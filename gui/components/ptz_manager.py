# gui/components/ptz_manager.py
"""
Gestión completa de funcionalidades PTZ.
Responsabilidades:
- Gestión de cámaras PTZ y conexiones
- Control de movimientos PTZ (presets, absolutos, continuos)
- Trigger automático de movimientos basado en detecciones
- Gestión de credenciales y configuración PTZ
- Integración con sistemas de automatización
"""

import json
import time
from typing import Dict, List, Optional, Any, Tuple
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtWidgets import QMessageBox


class PTZManager(QObject):
    """Gestor completo de funcionalidades PTZ"""
    
    # Señales
    ptz_moved = pyqtSignal(str, dict)  # IP, configuración
    ptz_error = pyqtSignal(str, str)   # IP, error
    ptz_status_changed = pyqtSignal(str, str)  # IP, status
    log_message = pyqtSignal(str)      # Mensaje de log
    
    def __init__(self, parent=None, config_file_path="config.json"):
        super().__init__(parent)
        self.parent_widget = parent
        self.config_file_path = config_file_path
        
        # Cámaras PTZ disponibles
        self.ptz_cameras: List[str] = []
        self.ptz_objects: Dict[str, Any] = {}  # IP:puerto -> instancia PTZ
        self.credentials_cache: Dict[str, Dict[str, Any]] = {}
        
        # Configuración de automatización
        self.auto_trigger_enabled = True
        self.ptz_cooldown = 2.0  # Segundos entre movimientos automáticos
        self.last_ptz_moves: Dict[str, float] = {}  # IP -> timestamp
        
        # Timer para operaciones diferidas
        self.deferred_timer = QTimer()
        self.deferred_timer.setSingleShot(True)
        self.deferred_operations = []
        
        # Cargar configuración inicial
        self._load_ptz_configuration()
    
    def _emit_log(self, message: str):
        """Emite mensaje de log"""
        self.log_message.emit(message)
        if self.parent_widget and hasattr(self.parent_widget, 'registrar_log'):
            self.parent_widget.registrar_log(message)
    
    # === GESTIÓN DE CONFIGURACIÓN ===
    
    def _load_ptz_configuration(self):
        """Carga la configuración de cámaras PTZ desde archivo"""
        try:
            with open(self.config_file_path, 'r') as f:
                config_data = json.load(f)
            
            self.ptz_cameras.clear()
            self.credentials_cache.clear()
            
            camaras_config = config_data.get("camaras", [])
            for cam_config in camaras_config:
                ip = cam_config.get("ip")
                tipo = cam_config.get("tipo")
                
                if tipo == "ptz" and ip:
                    if ip not in self.ptz_cameras:
                        self.ptz_cameras.append(ip)
                    
                    # Almacenar credenciales en caché
                    self.credentials_cache[ip] = {
                        "usuario": cam_config.get("usuario", "admin"),
                        "contrasena": cam_config.get("contrasena", ""),
                        "puerto": cam_config.get("puerto", 80),
                        "tipo": tipo,
                        "modelo": cam_config.get("modelo", ""),
                        "rtsp_port": cam_config.get("rtsp_port", 554)
                    }
            
            self._emit_log(f"🔄 Cámaras PTZ cargadas: {len(self.ptz_cameras)} encontradas")
            for ip in self.ptz_cameras:
                self._emit_log(f"   📷 PTZ disponible: {ip}")
                
        except FileNotFoundError:
            self._emit_log(f"⚠️ Archivo de configuración no encontrado: {self.config_file_path}")
        except json.JSONDecodeError as e:
            self._emit_log(f"❌ Error leyendo configuración JSON: {e}")
        except Exception as e:
            self._emit_log(f"❌ Error cargando configuración PTZ: {e}")
    
    def reload_ptz_configuration(self):
        """Recarga la configuración PTZ"""
        self._load_ptz_configuration()
    
    def get_ptz_cameras(self) -> List[str]:
        """Obtiene lista de IPs de cámaras PTZ"""
        return self.ptz_cameras.copy()
    
    def get_camera_credentials(self, ip: str) -> Optional[Dict[str, Any]]:
        """Obtiene las credenciales de una cámara PTZ"""
        return self.credentials_cache.get(ip)
    
    def get_camera_info(self, ip: str) -> Optional[Dict[str, Any]]:
        """Obtiene información detallada de una cámara PTZ"""
        return self.credentials_cache.get(ip)
    
    # === GESTIÓN DE CONEXIONES PTZ ===
    
    def _get_ptz_instance(self, ip: str) -> Optional[Any]:
        """Obtiene o crea una instancia PTZ para la IP especificada"""
        credentials = self.get_camera_credentials(ip)
        if not credentials:
            self._emit_log(f"❌ No se encontraron credenciales para PTZ {ip}")
            return None
        
        # Crear clave única para la conexión
        key = f"{ip}:{credentials['puerto']}"
        
        # Si ya existe la instancia, devolverla
        if key in self.ptz_objects:
            return self.ptz_objects[key]
        
        # Crear nueva instancia PTZ
        try:
            # Importar dinámicamente para evitar errores si no está disponible
            from core.ptz_camera_onvif import PTZCameraONVIF
            
            ptz_instance = PTZCameraONVIF(
                ip=ip,
                port=credentials['puerto'],
                username=credentials['usuario'],
                password=credentials['contrasena']
            )
            
            # Probar la conexión
            if hasattr(ptz_instance, 'connect') and callable(ptz_instance.connect):
                if not ptz_instance.connect():
                    self._emit_log(f"❌ No se pudo conectar a PTZ {ip}")
                    return None
            
            self.ptz_objects[key] = ptz_instance
            self._emit_log(f"✅ PTZ {ip} conectado exitosamente")
            self.ptz_status_changed.emit(ip, "connected")
            
            return ptz_instance
            
        except ImportError:
            self._emit_log(f"❌ Módulo PTZ no disponible para {ip}")
            return None
        except Exception as e:
            self._emit_log(f"❌ Error conectando PTZ {ip}: {e}")
            self.ptz_error.emit(ip, str(e))
            return None
    
    def test_ptz_connection(self, ip: str) -> bool:
        """Prueba la conexión con una cámara PTZ"""
        self._emit_log(f"🧪 Probando conexión PTZ a {ip}...")
        
        instance = self._get_ptz_instance(ip)
        if instance:
            try:
                # Intentar obtener posición actual como prueba
                if hasattr(instance, 'get_position'):
                    position = instance.get_position()
                    self._emit_log(f"✅ PTZ {ip} respondió correctamente")
                    return True
                else:
                    # Si no tiene get_position, intentar stop como prueba simple
                    if hasattr(instance, 'stop'):
                        instance.stop()
                        self._emit_log(f"✅ PTZ {ip} responde a comandos")
                        return True
            except Exception as e:
                self._emit_log(f"❌ Error probando PTZ {ip}: {e}")
                return False
        
        return False
    
    def disconnect_ptz(self, ip: str) -> bool:
        """Desconecta una cámara PTZ específica"""
        credentials = self.get_camera_credentials(ip)
        if not credentials:
            return False
        
        key = f"{ip}:{credentials['puerto']}"
        if key in self.ptz_objects:
            try:
                instance = self.ptz_objects[key]
                if hasattr(instance, 'disconnect'):
                    instance.disconnect()
                del self.ptz_objects[key]
                self._emit_log(f"🔌 PTZ {ip} desconectado")
                self.ptz_status_changed.emit(ip, "disconnected")
                return True
            except Exception as e:
                self._emit_log(f"❌ Error desconectando PTZ {ip}: {e}")
        
        return False
    
    def disconnect_all_ptz(self):
        """Desconecta todas las cámaras PTZ"""
        for key in list(self.ptz_objects.keys()):
            ip = key.split(':')[0]
            self.disconnect_ptz(ip)
    
    # === CONTROL PTZ BÁSICO ===
    
    def move_to_preset(self, ip: str, preset: str) -> bool:
        """Mueve la cámara PTZ a un preset específico"""
        instance = self._get_ptz_instance(ip)
        if not instance:
            return False
        
        try:
            if hasattr(instance, 'goto_preset'):
                success = instance.goto_preset(preset)
                if success:
                    self._emit_log(f"✅ PTZ {ip} movido a preset {preset}")
                    self.ptz_moved.emit(ip, {"type": "preset", "preset": preset})
                    return True
                else:
                    self._emit_log(f"❌ Error moviendo PTZ {ip} a preset {preset}")
            else:
                self._emit_log(f"❌ PTZ {ip} no soporta presets")
        except Exception as e:
            self._emit_log(f"❌ Error moviendo PTZ {ip} a preset {preset}: {e}")
            self.ptz_error.emit(ip, str(e))
        
        return False
    
    def move_absolute(self, ip: str, pan: float, tilt: float, zoom: float = None, speed: float = 0.5) -> bool:
        """Mueve la cámara PTZ a una posición absoluta"""
        instance = self._get_ptz_instance(ip)
        if not instance:
            return False
        
        try:
            if hasattr(instance, 'absolute_move'):
                success = instance.absolute_move(pan, tilt, zoom, speed)
                if success:
                    self._emit_log(f"✅ PTZ {ip} movido a posición absoluta (pan:{pan:.2f}, tilt:{tilt:.2f}, zoom:{zoom})")
                    self.ptz_moved.emit(ip, {
                        "type": "absolute",
                        "pan": pan,
                        "tilt": tilt,
                        "zoom": zoom,
                        "speed": speed
                    })
                    return True
                else:
                    self._emit_log(f"❌ Error en movimiento absoluto PTZ {ip}")
            else:
                self._emit_log(f"❌ PTZ {ip} no soporta movimiento absoluto")
        except Exception as e:
            self._emit_log(f"❌ Error movimiento absoluto PTZ {ip}: {e}")
            self.ptz_error.emit(ip, str(e))
        
        return False
    
    def move_continuous(self, ip: str, pan_speed: float, tilt_speed: float, 
                       zoom_speed: float = 0.0, duration: float = None) -> bool:
        """Mueve la cámara PTZ de forma continua"""
        instance = self._get_ptz_instance(ip)
        if not instance:
            return False
        
        try:
            if hasattr(instance, 'continuous_move'):
                success = instance.continuous_move(pan_speed, tilt_speed, zoom_speed, duration)
                if success:
                    self._emit_log(f"✅ PTZ {ip} movimiento continuo iniciado")
                    self.ptz_moved.emit(ip, {
                        "type": "continuous",
                        "pan_speed": pan_speed,
                        "tilt_speed": tilt_speed,
                        "zoom_speed": zoom_speed,
                        "duration": duration
                    })
                    return True
            else:
                self._emit_log(f"❌ PTZ {ip} no soporta movimiento continuo")
        except Exception as e:
            self._emit_log(f"❌ Error movimiento continuo PTZ {ip}: {e}")
            self.ptz_error.emit(ip, str(e))
        
        return False
    
    def stop_ptz(self, ip: str) -> bool:
        """Detiene el movimiento de la cámara PTZ"""
        instance = self._get_ptz_instance(ip)
        if not instance:
            return False
        
        try:
            if hasattr(instance, 'stop'):
                instance.stop()
                self._emit_log(f"⏹️ PTZ {ip} detenido")
                return True
        except Exception as e:
            self._emit_log(f"❌ Error deteniendo PTZ {ip}: {e}")
        
        return False
    
    def get_ptz_position(self, ip: str) -> Optional[Dict[str, float]]:
        """Obtiene la posición actual de la cámara PTZ"""
        instance = self._get_ptz_instance(ip)
        if not instance:
            return None
        
        try:
            if hasattr(instance, 'get_position'):
                position = instance.get_position()
                if position:
                    self._emit_log(f"📍 Posición PTZ {ip}: {position}")
                    return position
        except Exception as e:
            self._emit_log(f"❌ Error obteniendo posición PTZ {ip}: {e}")
        
        return None
    
    # === GESTIÓN DE PRESETS ===
    
    def create_preset(self, ip: str, preset_token: str, preset_name: str = None) -> bool:
        """Crea un preset en la posición actual"""
        instance = self._get_ptz_instance(ip)
        if not instance:
            return False
        
        try:
            if hasattr(instance, 'set_preset'):
                success = instance.set_preset(preset_token, preset_name)
                if success:
                    self._emit_log(f"✅ Preset {preset_token} creado en PTZ {ip}")
                    return True
        except Exception as e:
            self._emit_log(f"❌ Error creando preset en PTZ {ip}: {e}")
        
        return False
    
    def delete_preset(self, ip: str, preset_token: str) -> bool:
        """Elimina un preset"""
        instance = self._get_ptz_instance(ip)
        if not instance:
            return False
        
        try:
            if hasattr(instance, 'remove_preset'):
                success = instance.remove_preset(preset_token)
                if success:
                    self._emit_log(f"✅ Preset {preset_token} eliminado de PTZ {ip}")
                    return True
        except Exception as e:
            self._emit_log(f"❌ Error eliminando preset de PTZ {ip}: {e}")
        
        return False
    
    def get_presets(self, ip: str) -> Optional[Dict[str, str]]:
        """Obtiene la lista de presets disponibles"""
        instance = self._get_ptz_instance(ip)
        if not instance:
            return None
        
        try:
            if hasattr(instance, 'get_presets'):
                presets = instance.get_presets()
                if presets:
                    self._emit_log(f"📋 Presets PTZ {ip}: {len(presets)} encontrados")
                    return presets
        except Exception as e:
            self._emit_log(f"❌ Error obteniendo presets PTZ {ip}: {e}")
        
        return None
    
    # === AUTOMATIZACIÓN PTZ ===
    
    def set_auto_trigger_enabled(self, enabled: bool):
        """Habilita/deshabilita el trigger automático"""
        self.auto_trigger_enabled = enabled
        status = "habilitado" if enabled else "deshabilitado"
        self._emit_log(f"🔄 Trigger automático PTZ {status}")
    
    def set_ptz_cooldown(self, cooldown: float):
        """Establece el tiempo de cooldown entre movimientos automáticos"""
        self.ptz_cooldown = max(0.5, cooldown)  # Mínimo 0.5 segundos
        self._emit_log(f"⏱️ Cooldown PTZ establecido a {self.ptz_cooldown}s")
    
    def _check_cooldown(self, ip: str) -> bool:
        """Verifica si ha pasado suficiente tiempo para mover la PTZ"""
        current_time = time.time()
        last_move = self.last_ptz_moves.get(ip, 0)
        
        if current_time - last_move >= self.ptz_cooldown:
            self.last_ptz_moves[ip] = current_time
            return True
        
        return False
    
    def trigger_automatic_move(self, ip: str, config: Dict[str, Any], 
                             cell_coords: Tuple[int, int] = None) -> bool:
        """
        Trigger automático de movimiento PTZ basado en detección
        
        Args:
            ip: IP de la cámara PTZ
            config: Configuración del movimiento (preset, absoluto, etc.)
            cell_coords: Coordenadas de la celda que activó el trigger
        """
        if not self.auto_trigger_enabled:
            return False
        
        # Verificar cooldown
        if not self._check_cooldown(ip):
            return False
        
        move_type = config.get("type", "preset")
        
        try:
            if move_type == "preset":
                preset = config.get("preset")
                if preset:
                    success = self.move_to_preset(ip, preset)
                    if success and cell_coords:
                        self._emit_log(f"🎯 Trigger automático: PTZ {ip} → preset {preset} (celda {cell_coords})")
                    return success
            
            elif move_type == "absolute" or move_type == "absolute_with_zoom":
                pan = config.get("pan", 0)
                tilt = config.get("tilt", 0)
                zoom = config.get("zoom")
                speed = config.get("speed", 0.8)
                
                success = self.move_absolute(ip, pan, tilt, zoom, speed)
                if success and cell_coords:
                    zoom_info = f", zoom: {zoom*100:.0f}%" if zoom else ""
                    self._emit_log(f"🎯 Trigger automático: PTZ {ip} → absoluto (pan:{pan:.2f}, tilt:{tilt:.2f}{zoom_info}) (celda {cell_coords})")
                return success
            
            elif move_type == "continuous":
                pan_speed = config.get("pan_speed", 0)
                tilt_speed = config.get("tilt_speed", 0)
                zoom_speed = config.get("zoom_speed", 0)
                duration = config.get("duration", 2.0)
                
                success = self.move_continuous(ip, pan_speed, tilt_speed, zoom_speed, duration)
                if success and cell_coords:
                    self._emit_log(f"🎯 Trigger automático: PTZ {ip} → continuo (celda {cell_coords})")
                return success
            
            else:
                self._emit_log(f"❌ Tipo de movimiento PTZ no soportado: {move_type}")
                return False
                
        except Exception as e:
            self._emit_log(f"❌ Error en trigger automático PTZ {ip}: {e}")
            self.ptz_error.emit(ip, str(e))
            return False
    
    # === OPERACIONES AVANZADAS ===
    
    def patrol_presets(self, ip: str, preset_list: List[str], 
                      hold_time: float = 5.0, cycles: int = 1) -> bool:
        """Ejecuta una patrulla entre presets"""
        instance = self._get_ptz_instance(ip)
        if not instance or len(preset_list) < 2:
            return False
        
        try:
            if hasattr(instance, 'patrol_between_presets'):
                success = instance.patrol_between_presets(preset_list, hold_time, cycles)
                if success:
                    self._emit_log(f"🚶 Patrulla iniciada en PTZ {ip}: {len(preset_list)} presets, {cycles} ciclos")
                return success
        except Exception as e:
            self._emit_log(f"❌ Error iniciando patrulla PTZ {ip}: {e}")
        
        return False
    
    def smooth_move_to_position(self, ip: str, target_pan: float, target_tilt: float, 
                               target_zoom: float = None, steps: int = 5, delay: float = 0.2) -> bool:
        """Movimiento suave a una posición"""
        instance = self._get_ptz_instance(ip)
        if not instance:
            return False
        
        try:
            if hasattr(instance, 'smooth_move_to_position'):
                success = instance.smooth_move_to_position(target_pan, target_tilt, target_zoom, steps, delay)
                if success:
                    self._emit_log(f"🎯 Movimiento suave completado en PTZ {ip}")
                return success
        except Exception as e:
            self._emit_log(f"❌ Error movimiento suave PTZ {ip}: {e}")
        
        return False
    
    # === ESTADÍSTICAS Y ESTADO ===
    
    def get_ptz_status(self, ip: str) -> Dict[str, Any]:
        """Obtiene el estado completo de una PTZ"""
        credentials = self.get_camera_credentials(ip)
        if not credentials:
            return {"status": "not_configured"}
        
        key = f"{ip}:{credentials['puerto']}"
        connected = key in self.ptz_objects
        
        status = {
            "ip": ip,
            "credentials": credentials,
            "connected": connected,
            "last_move": self.last_ptz_moves.get(ip, 0),
            "cooldown_remaining": max(0, self.ptz_cooldown - (time.time() - self.last_ptz_moves.get(ip, 0)))
        }
        
        if connected:
            try:
                position = self.get_ptz_position(ip)
                if position:
                    status["current_position"] = position
            except:
                pass
        
        return status
    
    def get_all_ptz_status(self) -> Dict[str, Dict[str, Any]]:
        """Obtiene el estado de todas las PTZ"""
        return {ip: self.get_ptz_status(ip) for ip in self.ptz_cameras}
    
    def get_statistics(self) -> Dict[str, Any]:
        """Obtiene estadísticas del sistema PTZ"""
        connected_count = len(self.ptz_objects)
        total_count = len(self.ptz_cameras)
        
        return {
            "total_ptz_cameras": total_count,
            "connected_ptz_cameras": connected_count,
            "auto_trigger_enabled": self.auto_trigger_enabled,
            "ptz_cooldown": self.ptz_cooldown,
            "active_connections": list(self.ptz_objects.keys()),
            "recent_moves": len([t for t in self.last_ptz_moves.values() 
                               if time.time() - t < 60])  # Movimientos en último minuto
        }
    
    # === UTILIDADES ===
    
    def validate_ptz_configuration(self) -> Dict[str, List[str]]:
        """Valida la configuración PTZ y retorna errores/advertencias"""
        errors = []
        warnings = []
        
        if not self.ptz_cameras:
            warnings.append("No hay cámaras PTZ configuradas")
        
        for ip in self.ptz_cameras:
            credentials = self.get_camera_credentials(ip)
            if not credentials:
                errors.append(f"Sin credenciales para PTZ {ip}")
                continue
            
            if not credentials.get("usuario"):
                warnings.append(f"PTZ {ip} sin usuario configurado")
            
            if not credentials.get("contrasena"):
                warnings.append(f"PTZ {ip} sin contraseña configurada")
        
        return {"errors": errors, "warnings": warnings}
    
    def cleanup(self):
        """Limpia recursos y desconecta todas las PTZ"""
        self._emit_log("🧹 Limpiando recursos PTZ...")
        self.disconnect_all_ptz()
        if self.deferred_timer.isActive():
            self.deferred_timer.stop()