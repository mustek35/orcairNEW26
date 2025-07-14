# gui/components/config_manager.py
"""
Gestión de configuración y persistencia.
Responsabilidades:
- Carga y guardado de configuración desde/hacia archivos
- Gestión de configuración de cámaras
- Persistencia de estados de celdas
- Configuración de PTZ y presets
- Backup y restauración
- Migración de configuraciones
"""

import json
import os
import shutil
import time
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from PyQt6.QtCore import QObject, pyqtSignal
from pathlib import Path


class ConfigManager(QObject):
    """Gestor de configuración y persistencia"""
    
    # Señales
    config_loaded = pyqtSignal(dict)  # Configuración cargada
    config_saved = pyqtSignal(str)    # Ruta donde se guardó
    config_error = pyqtSignal(str)    # Error en configuración
    log_message = pyqtSignal(str)     # Mensaje de log
    
    def __init__(self, config_file_path="config.json", parent=None):
        super().__init__(parent)
        self.config_file_path = Path(config_file_path)
        self.backup_dir = Path("config_backups")
        
        # Configuración actual en memoria
        self.current_config: Dict[str, Any] = {}
        
        # Configuración por defecto
        self.default_config = {
            "version": "1.0",
            "created": datetime.now().isoformat(),
            "camaras": [],
            "grid_settings": {
                "filas": 18,
                "columnas": 22,
                "cell_presets": {},
                "cell_ptz_map": {},
                "discarded_cells": [],
                "selected_cells": [],
                "temporal_cells": []
            },
            "ptz_settings": {
                "auto_trigger_enabled": True,
                "ptz_cooldown": 2.0,
                "default_zoom": 0.4,
                "movement_threshold": 20
            },
            "detection_settings": {
                "confidence_threshold": 0.5,
                "min_object_size": 100,
                "detection_cooldown": 1.0,
                "debug_enabled": False
            },
            "visual_settings": {
                "theme": "dark",
                "grid_lines_enabled": True,
                "animations_enabled": True,
                "adaptive_info_enabled": False
            },
            "system_settings": {
                "auto_save_interval": 300,  # 5 minutos
                "max_backups": 10,
                "log_level": "INFO"
            }
        }
        
        # Estado de auto-guardado
        self.auto_save_enabled = True
        self.last_save_time = 0
        self.unsaved_changes = False
        
        # Crear directorio de backups si no existe
        self.backup_dir.mkdir(exist_ok=True)
        
    def _emit_log(self, message: str):
        """Emite mensaje de log"""
        self.log_message.emit(message)
    
    # === CARGA DE CONFIGURACIÓN ===
    
    def load_configuration(self) -> Dict[str, Any]:
        """
        Carga la configuración desde archivo
        
        Returns:
            Diccionario con la configuración cargada
        """
        try:
            if not self.config_file_path.exists():
                self._emit_log(f"📄 Archivo de configuración no encontrado: {self.config_file_path}")
                self._emit_log("🔧 Creando configuración por defecto...")
                return self._create_default_config()
            
            with open(self.config_file_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Validar y migrar configuración si es necesario
            validated_config = self._validate_and_migrate_config(config_data)
            
            self.current_config = validated_config
            self.unsaved_changes = False
            self.last_save_time = time.time()
            
            self._emit_log(f"✅ Configuración cargada desde: {self.config_file_path}")
            self.config_loaded.emit(validated_config)
            
            return validated_config
            
        except json.JSONDecodeError as e:
            self._emit_log(f"❌ Error de formato JSON: {e}")
            return self._handle_corrupted_config()
        except Exception as e:
            self._emit_log(f"❌ Error cargando configuración: {e}")
            self.config_error.emit(str(e))
            return self._create_default_config()
    
    def _create_default_config(self) -> Dict[str, Any]:
        """Crea configuración por defecto"""
        self.current_config = self.default_config.copy()
        self.unsaved_changes = True
        
        # Guardar configuración por defecto
        self.save_configuration()
        
        return self.current_config
    
    def _validate_and_migrate_config(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Valida y migra configuración a la versión actual"""
        # Detectar versión
        version = config_data.get("version", "0.9")
        
        if version != self.default_config["version"]:
            self._emit_log(f"🔄 Migrando configuración de v{version} a v{self.default_config['version']}")
            config_data = self._migrate_config(config_data, version)
        
        # Asegurar que todas las secciones existen
        for section, default_values in self.default_config.items():
            if section not in config_data:
                config_data[section] = default_values
                self._emit_log(f"➕ Sección agregada: {section}")
            elif isinstance(default_values, dict):
                # Merge de configuraciones anidadas
                for key, value in default_values.items():
                    if key not in config_data[section]:
                        config_data[section][key] = value
                        self._emit_log(f"➕ Configuración agregada: {section}.{key}")
        
        return config_data
    
    def _migrate_config(self, config_data: Dict[str, Any], from_version: str) -> Dict[str, Any]:
        """Migra configuración desde versión anterior"""
        migrated_config = config_data.copy()
        
        # Crear backup antes de migración
        backup_path = self._create_backup(f"migration_from_v{from_version}")
        self._emit_log(f"💾 Backup de migración creado: {backup_path}")
        
        # Migración específica por versión
        if from_version == "0.9":
            migrated_config = self._migrate_from_v09(migrated_config)
        
        # Actualizar versión
        migrated_config["version"] = self.default_config["version"]
        migrated_config["migrated_from"] = from_version
        migrated_config["migration_date"] = datetime.now().isoformat()
        
        return migrated_config
    
    def _migrate_from_v09(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Migración específica desde v0.9"""
        # Reorganizar estructura de cámaras si es necesario
        if "camaras" in config_data:
            for camera in config_data["camaras"]:
                # Agregar campos nuevos con valores por defecto
                if "rtsp_port" not in camera:
                    camera["rtsp_port"] = 554
                if "modelo" not in camera:
                    camera["modelo"] = ""
        
        # Migrar configuración de grilla si existe en formato anterior
        if "celdas_descartadas" in config_data:
            if "grid_settings" not in config_data:
                config_data["grid_settings"] = {}
            config_data["grid_settings"]["discarded_cells"] = config_data.pop("celdas_descartadas")
        
        return config_data
    
    def _handle_corrupted_config(self) -> Dict[str, Any]:
        """Maneja configuración corrupta"""
        # Crear backup del archivo corrupto
        corrupted_backup = self.config_file_path.with_suffix(f".corrupted_{int(time.time())}")
        shutil.copy2(self.config_file_path, corrupted_backup)
        
        self._emit_log(f"💾 Archivo corrupto respaldado como: {corrupted_backup}")
        self._emit_log("🔧 Creando nueva configuración por defecto...")
        
        return self._create_default_config()
    
    # === GUARDADO DE CONFIGURACIÓN ===
    
    def save_configuration(self, config_data: Optional[Dict[str, Any]] = None) -> bool:
        """
        Guarda la configuración actual
        
        Args:
            config_data: Configuración a guardar (usa current_config si es None)
            
        Returns:
            True si se guardó exitosamente
        """
        try:
            if config_data is None:
                config_data = self.current_config
            
            # Actualizar timestamp
            config_data["last_modified"] = datetime.now().isoformat()
            
            # Crear backup antes de guardar
            if self.config_file_path.exists():
                self._create_backup("auto")
            
            # Crear directorio si no existe
            self.config_file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Guardar con formato bonito
            with open(self.config_file_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            self.current_config = config_data
            self.unsaved_changes = False
            self.last_save_time = time.time()
            
            self._emit_log(f"💾 Configuración guardada en: {self.config_file_path}")
            self.config_saved.emit(str(self.config_file_path))
            
            return True
            
        except Exception as e:
            self._emit_log(f"❌ Error guardando configuración: {e}")
            self.config_error.emit(str(e))
            return False
    
    def mark_unsaved_changes(self):
        """Marca que hay cambios sin guardar"""
        self.unsaved_changes = True
    
    def has_unsaved_changes(self) -> bool:
        """Verifica si hay cambios sin guardar"""
        return self.unsaved_changes
    
    # === GESTIÓN DE CÁMARAS ===
    
    def add_camera(self, camera_config: Dict[str, Any]) -> bool:
        """Agrega una nueva cámara a la configuración"""
        try:
            if "camaras" not in self.current_config:
                self.current_config["camaras"] = []
            
            # Verificar que no exista una cámara con la misma IP
            ip = camera_config.get("ip")
            if ip and any(cam.get("ip") == ip for cam in self.current_config["camaras"]):
                self._emit_log(f"⚠️ Ya existe una cámara con IP: {ip}")
                return False
            
            # Agregar timestamp
            camera_config["added"] = datetime.now().isoformat()
            
            self.current_config["camaras"].append(camera_config)
            self.mark_unsaved_changes()
            
            self._emit_log(f"📷 Cámara agregada: {ip} ({camera_config.get('tipo', 'unknown')})")
            return True
            
        except Exception as e:
            self._emit_log(f"❌ Error agregando cámara: {e}")
            return False
    
    def remove_camera(self, camera_ip: str) -> bool:
        """Remueve una cámara de la configuración"""
        try:
            if "camaras" not in self.current_config:
                return False
            
            initial_count = len(self.current_config["camaras"])
            self.current_config["camaras"] = [
                cam for cam in self.current_config["camaras"] 
                if cam.get("ip") != camera_ip
            ]
            
            removed = len(self.current_config["camaras"]) < initial_count
            if removed:
                self.mark_unsaved_changes()
                self._emit_log(f"🗑️ Cámara removida: {camera_ip}")
            
            return removed
            
        except Exception as e:
            self._emit_log(f"❌ Error removiendo cámara: {e}")
            return False
    
    def update_camera(self, camera_ip: str, updates: Dict[str, Any]) -> bool:
        """Actualiza configuración de una cámara"""
        try:
            if "camaras" not in self.current_config:
                return False
            
            for camera in self.current_config["camaras"]:
                if camera.get("ip") == camera_ip:
                    camera.update(updates)
                    camera["last_modified"] = datetime.now().isoformat()
                    self.mark_unsaved_changes()
                    
                    self._emit_log(f"📝 Cámara actualizada: {camera_ip}")
                    return True
            
            return False
            
        except Exception as e:
            self._emit_log(f"❌ Error actualizando cámara: {e}")
            return False
    
    def get_cameras(self, camera_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Obtiene lista de cámaras, opcionalmente filtrada por tipo"""
        cameras = self.current_config.get("camaras", [])
        
        if camera_type:
            cameras = [cam for cam in cameras if cam.get("tipo") == camera_type]
        
        return cameras
    
    def get_camera(self, camera_ip: str) -> Optional[Dict[str, Any]]:
        """Obtiene configuración de una cámara específica"""
        for camera in self.current_config.get("camaras", []):
            if camera.get("ip") == camera_ip:
                return camera
        return None
    
    # === GESTIÓN DE GRILLA ===
    
    def save_grid_state(self, cell_manager) -> bool:
        """Guarda el estado completo de la grilla"""
        try:
            grid_state = cell_manager.to_dict()
            self.current_config["grid_settings"] = grid_state
            self.mark_unsaved_changes()
            
            stats = cell_manager.get_statistics()
            self._emit_log(f"📐 Estado de grilla guardado: {stats['total_cells']} celdas")
            return True
            
        except Exception as e:
            self._emit_log(f"❌ Error guardando estado de grilla: {e}")
            return False
    
    def load_grid_state(self, cell_manager) -> bool:
        """Carga el estado de la grilla"""
        try:
            grid_settings = self.current_config.get("grid_settings", {})
            if not grid_settings:
                return False
            
            cell_manager.from_dict(grid_settings)
            self._emit_log(f"📐 Estado de grilla cargado")
            return True
            
        except Exception as e:
            self._emit_log(f"❌ Error cargando estado de grilla: {e}")
            return False
    
    # === GESTIÓN DE CONFIGURACIONES ESPECÍFICAS ===
    
    def get_ptz_settings(self) -> Dict[str, Any]:
        """Obtiene configuración PTZ"""
        return self.current_config.get("ptz_settings", self.default_config["ptz_settings"])
    
    def update_ptz_settings(self, updates: Dict[str, Any]) -> bool:
        """Actualiza configuración PTZ"""
        try:
            if "ptz_settings" not in self.current_config:
                self.current_config["ptz_settings"] = {}
            
            self.current_config["ptz_settings"].update(updates)
            self.mark_unsaved_changes()
            
            self._emit_log("🎯 Configuración PTZ actualizada")
            return True
            
        except Exception as e:
            self._emit_log(f"❌ Error actualizando configuración PTZ: {e}")
            return False
    
    def get_detection_settings(self) -> Dict[str, Any]:
        """Obtiene configuración de detección"""
        return self.current_config.get("detection_settings", self.default_config["detection_settings"])
    
    def update_detection_settings(self, updates: Dict[str, Any]) -> bool:
        """Actualiza configuración de detección"""
        try:
            if "detection_settings" not in self.current_config:
                self.current_config["detection_settings"] = {}
            
            self.current_config["detection_settings"].update(updates)
            self.mark_unsaved_changes()
            
            self._emit_log("🔍 Configuración de detección actualizada")
            return True
            
        except Exception as e:
            self._emit_log(f"❌ Error actualizando configuración de detección: {e}")
            return False
    
    def get_visual_settings(self) -> Dict[str, Any]:
        """Obtiene configuración visual"""
        return self.current_config.get("visual_settings", self.default_config["visual_settings"])
    
    def update_visual_settings(self, updates: Dict[str, Any]) -> bool:
        """Actualiza configuración visual"""
        try:
            if "visual_settings" not in self.current_config:
                self.current_config["visual_settings"] = {}
            
            self.current_config["visual_settings"].update(updates)
            self.mark_unsaved_changes()
            
            self._emit_log("🎨 Configuración visual actualizada")
            return True
            
        except Exception as e:
            self._emit_log(f"❌ Error actualizando configuración visual: {e}")
            return False
    
    # === BACKUP Y RESTAURACIÓN ===
    
    def _create_backup(self, backup_type: str = "manual") -> Optional[Path]:
        """Crea backup de la configuración actual"""
        try:
            if not self.config_file_path.exists():
                return None
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"config_{backup_type}_{timestamp}.json"
            backup_path = self.backup_dir / backup_filename
            
            shutil.copy2(self.config_file_path, backup_path)
            
            # Limpiar backups antiguos
            self._cleanup_old_backups()
            
            return backup_path
            
        except Exception as e:
            self._emit_log(f"❌ Error creando backup: {e}")
            return None
    
    def create_manual_backup(self, name: Optional[str] = None) -> Optional[Path]:
        """Crea backup manual con nombre opcional"""
        backup_type = f"manual_{name}" if name else "manual"
        backup_path = self._create_backup(backup_type)
        
        if backup_path:
            self._emit_log(f"💾 Backup manual creado: {backup_path}")
        
        return backup_path
    
    def list_backups(self) -> List[Tuple[Path, datetime]]:
        """Lista todos los backups disponibles"""
        backups = []
        
        for backup_file in self.backup_dir.glob("config_*.json"):
            try:
                mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)
                backups.append((backup_file, mtime))
            except:
                continue
        
        # Ordenar por fecha (más reciente primero)
        backups.sort(key=lambda x: x[1], reverse=True)
        return backups
    
    def restore_from_backup(self, backup_path: Path) -> bool:
        """Restaura configuración desde backup"""
        try:
            if not backup_path.exists():
                self._emit_log(f"❌ Backup no encontrado: {backup_path}")
                return False
            
            # Crear backup de la configuración actual antes de restaurar
            current_backup = self._create_backup("before_restore")
            
            # Restaurar
            shutil.copy2(backup_path, self.config_file_path)
            
            # Recargar configuración
            self.load_configuration()
            
            self._emit_log(f"🔄 Configuración restaurada desde: {backup_path}")
            return True
            
        except Exception as e:
            self._emit_log(f"❌ Error restaurando backup: {e}")
            return False
    
    def _cleanup_old_backups(self):
        """Limpia backups antiguos manteniendo solo los más recientes"""
        try:
            max_backups = self.current_config.get("system_settings", {}).get("max_backups", 10)
            backups = self.list_backups()
            
            if len(backups) > max_backups:
                for backup_path, _ in backups[max_backups:]:
                    backup_path.unlink()
                    self._emit_log(f"🗑️ Backup antiguo eliminado: {backup_path.name}")
                    
        except Exception as e:
            self._emit_log(f"❌ Error limpiando backups: {e}")
    
    # === EXPORTACIÓN E IMPORTACIÓN ===
    
    def export_configuration(self, export_path: Path, include_sensitive: bool = False) -> bool:
        """Exporta configuración a archivo específico"""
        try:
            export_config = self.current_config.copy()
            
            # Remover información sensible si se solicita
            if not include_sensitive:
                if "camaras" in export_config:
                    for camera in export_config["camaras"]:
                        if "contrasena" in camera:
                            camera["contrasena"] = "***REMOVED***"
            
            # Agregar metadata de exportación
            export_config["export_info"] = {
                "exported_at": datetime.now().isoformat(),
                "exported_by": "PTZ Control System",
                "original_file": str(self.config_file_path),
                "includes_sensitive": include_sensitive
            }
            
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(export_config, f, indent=2, ensure_ascii=False)
            
            self._emit_log(f"📤 Configuración exportada a: {export_path}")
            return True
            
        except Exception as e:
            self._emit_log(f"❌ Error exportando configuración: {e}")
            return False
    
    def import_configuration(self, import_path: Path, merge: bool = False) -> bool:
        """Importa configuración desde archivo"""
        try:
            if not import_path.exists():
                self._emit_log(f"❌ Archivo de importación no encontrado: {import_path}")
                return False
            
            with open(import_path, 'r', encoding='utf-8') as f:
                imported_config = json.load(f)
            
            # Crear backup antes de importar
            self._create_backup("before_import")
            
            if merge:
                # Merge con configuración actual
                self._merge_configurations(imported_config)
            else:
                # Reemplazar completamente
                self.current_config = imported_config
            
            # Validar y migrar
            self.current_config = self._validate_and_migrate_config(self.current_config)
            
            # Guardar
            self.save_configuration()
            
            self._emit_log(f"📥 Configuración importada desde: {import_path}")
            return True
            
        except Exception as e:
            self._emit_log(f"❌ Error importando configuración: {e}")
            return False
    
    def _merge_configurations(self, imported_config: Dict[str, Any]):
        """Merge configuración importada con la actual"""
        for section, values in imported_config.items():
            if section == "camaras":
                # Merge especial para cámaras (evitar duplicados)
                existing_ips = {cam.get("ip") for cam in self.current_config.get("camaras", [])}
                for imported_camera in values:
                    if imported_camera.get("ip") not in existing_ips:
                        self.current_config.setdefault("camaras", []).append(imported_camera)
            elif isinstance(values, dict):
                # Merge recursivo para diccionarios
                self.current_config.setdefault(section, {}).update(values)
            else:
                # Reemplazar valor directamente
                self.current_config[section] = values
    
    # === UTILIDADES ===
    
    def validate_configuration(self) -> Dict[str, List[str]]:
        """Valida la configuración actual y retorna errores/advertencias"""
        errors = []
        warnings = []
        
        # Validar estructura básica
        required_sections = ["camaras", "grid_settings", "ptz_settings"]
        for section in required_sections:
            if section not in self.current_config:
                errors.append(f"Sección faltante: {section}")
        
        # Validar cámaras
        cameras = self.current_config.get("camaras", [])
        camera_ips = []
        
        for i, camera in enumerate(cameras):
            ip = camera.get("ip")
            if not ip:
                errors.append(f"Cámara {i}: IP faltante")
            elif ip in camera_ips:
                errors.append(f"Cámara {i}: IP duplicada: {ip}")
            else:
                camera_ips.append(ip)
            
            if not camera.get("usuario"):
                warnings.append(f"Cámara {ip}: Usuario no configurado")
            
            if not camera.get("contrasena"):
                warnings.append(f"Cámara {ip}: Contraseña no configurada")
        
        # Validar configuración PTZ
        ptz_settings = self.current_config.get("ptz_settings", {})
        if ptz_settings.get("ptz_cooldown", 0) < 0.5:
            warnings.append("PTZ cooldown muy bajo (recomendado: >= 0.5s)")
        
        return {"errors": errors, "warnings": warnings}
    
    def get_configuration_summary(self) -> Dict[str, Any]:
        """Obtiene resumen de la configuración actual"""
        cameras = self.current_config.get("camaras", [])
        grid_settings = self.current_config.get("grid_settings", {})
        
        camera_types = {}
        for camera in cameras:
            cam_type = camera.get("tipo", "unknown")
            camera_types[cam_type] = camera_types.get(cam_type, 0) + 1
        
        return {
            "version": self.current_config.get("version", "unknown"),
            "total_cameras": len(cameras),
            "camera_types": camera_types,
            "grid_size": f"{grid_settings.get('filas', 0)}x{grid_settings.get('columnas', 0)}",
            "cells_with_ptz": len(grid_settings.get("cell_ptz_map", {})),
            "cells_with_presets": len(grid_settings.get("cell_presets", {})),
            "discarded_cells": len(grid_settings.get("discarded_cells", [])),
            "last_modified": self.current_config.get("last_modified", "unknown"),
            "file_size": self.config_file_path.stat().st_size if self.config_file_path.exists() else 0
        }
    
    def cleanup(self):
        """Limpia recursos y guarda cambios pendientes"""
        if self.unsaved_changes:
            self._emit_log("💾 Guardando cambios pendientes...")
            self.save_configuration()
        
        self._emit_log("🧹 ConfigManager limpiado")