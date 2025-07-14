# gui/components/detection_handler.py
"""
Procesamiento y gestión de detecciones.
Responsabilidades:
- Procesamiento de detecciones YOLO/IA
- Filtrado por movimiento y umbral
- Mapeo de detecciones a celdas de grilla
- Trigger automático de PTZ basado en detecciones
- Gestión de historial de objetos
- Filtrado de celdas descartadas
"""

import time
from typing import List, Dict, Any, Tuple, Set, Optional
from collections import defaultdict, deque
from PyQt6.QtCore import QObject, pyqtSignal, QSize
from PyQt6.QtGui import QImage


class DetectionHandler(QObject):
    """Gestor de procesamiento de detecciones"""
    
    # Señales
    detection_processed = pyqtSignal(list)  # Lista de detecciones procesadas
    movement_detected = pyqtSignal(int, int, dict)  # row, col, detection_info
    ptz_triggered = pyqtSignal(str, dict, tuple)  # ip, config, cell_coords
    alert_generated = pyqtSignal(dict)  # Información de alerta
    log_message = pyqtSignal(str)  # Mensaje de log
    
    def __init__(self, cell_manager, ptz_manager, parent=None):
        super().__init__(parent)
        self.cell_manager = cell_manager
        self.ptz_manager = ptz_manager
        self.parent_widget = parent
        
        # Configuración de detección
        self.umbral_movimiento = 20  # Píxeles mínimos de movimiento
        self.confidence_threshold = 0.5  # Confianza mínima
        self.min_object_size = 100  # Área mínima del objeto
        self.max_detections_per_frame = 50  # Máximo detecciones por frame
        
        # Historial de objetos para detectar movimiento
        self.objetos_previos: Dict[int, List[Tuple[float, float]]] = defaultdict(list)
        self.max_history_length = 10  # Máximo elementos en historial
        
        # Control de tiempo para evitar spam
        self.last_detection_time = {}
        self.detection_cooldown = 1.0  # Segundos entre detecciones por celda
        
        # Estadísticas
        self.stats = {
            "total_detections": 0,
            "filtered_detections": 0,
            "movement_detections": 0,
            "ptz_triggers": 0,
            "last_reset": time.time()
        }
        
        # Frame actual para contexto
        self.current_frame_size: Optional[QSize] = None
        self.current_frame_data: Optional[Any] = None
        
        # Debug
        self.debug_enabled = False
        
    def _emit_log(self, message: str):
        """Emite mensaje de log"""
        self.log_message.emit(message)
        if self.parent_widget and hasattr(self.parent_widget, 'registrar_log'):
            self.parent_widget.registrar_log(message)
    
    # === CONFIGURACIÓN ===
    
    def set_movement_threshold(self, threshold: int):
        """Establece el umbral de movimiento en píxeles"""
        self.umbral_movimiento = max(5, threshold)
        self._emit_log(f"🎯 Umbral de movimiento: {self.umbral_movimiento} píxeles")
    
    def set_confidence_threshold(self, threshold: float):
        """Establece el umbral de confianza mínima"""
        self.confidence_threshold = max(0.1, min(1.0, threshold))
        self._emit_log(f"🎯 Umbral de confianza: {self.confidence_threshold}")
    
    def set_min_object_size(self, size: int):
        """Establece el tamaño mínimo de objeto"""
        self.min_object_size = max(10, size)
        self._emit_log(f"🎯 Tamaño mínimo objeto: {self.min_object_size} píxeles²")
    
    def set_detection_cooldown(self, cooldown: float):
        """Establece el cooldown entre detecciones por celda"""
        self.detection_cooldown = max(0.1, cooldown)
        self._emit_log(f"🎯 Cooldown detección: {self.detection_cooldown}s")
    
    def enable_debug(self, enabled: bool):
        """Habilita/deshabilita modo debug"""
        self.debug_enabled = enabled
        status = "habilitado" if enabled else "deshabilitado"
        self._emit_log(f"🔧 Debug detecciones {status}")
    
    # === PROCESAMIENTO PRINCIPAL ===
    
    def set_frame_context(self, frame_size: QSize, frame_data: Any = None):
        """Establece el contexto del frame actual"""
        self.current_frame_size = frame_size
        self.current_frame_data = frame_data
    
    def process_detections(self, detections: List, frame_size: QSize = None) -> List:
        """
        Procesa una lista de detecciones y activa triggers PTZ si es necesario
        
        Args:
            detections: Lista de detecciones en formato (x1, y1, x2, y2, cls, cx, cy, track_id, conf)
            frame_size: Tamaño del frame para mapeo de celdas
            
        Returns:
            Lista de detecciones filtradas y procesadas
        """
        if frame_size:
            self.current_frame_size = frame_size
        
        if not self.current_frame_size:
            self._emit_log("⚠️ No hay contexto de frame para procesar detecciones")
            return []
        
        # Incrementar estadísticas
        self.stats["total_detections"] += len(detections)
        
        # Filtrar detecciones por calidad
        filtered_detections = self._filter_detections_by_quality(detections)
        
        # Detectar movimiento
        movement_detections = self._detect_movement(filtered_detections)
        
        # Mapear a celdas y activar PTZ
        processed_detections = self._process_cell_mapping(movement_detections)
        
        # Emitir señal con detecciones procesadas
        self.detection_processed.emit(processed_detections)
        
        if self.debug_enabled:
            self._log_processing_summary(detections, processed_detections)
        
        return processed_detections
    
    def _filter_detections_by_quality(self, detections: List) -> List:
        """Filtra detecciones por calidad (confianza, tamaño, etc.)"""
        filtered = []
        
        for detection in detections:
            if len(detection) < 9:  # Formato incompleto
                continue
            
            x1, y1, x2, y2, cls, cx, cy, track_id, conf = detection
            
            # Filtro por confianza
            if conf < self.confidence_threshold:
                continue
            
            # Filtro por tamaño
            width = abs(x2 - x1)
            height = abs(y2 - y1)
            area = width * height
            
            if area < self.min_object_size:
                continue
            
            # Filtro por posición válida
            if not (0 <= cx < self.current_frame_size.width() and 
                   0 <= cy < self.current_frame_size.height()):
                continue
            
            filtered.append(detection)
            
            if len(filtered) >= self.max_detections_per_frame:
                break
        
        self.stats["filtered_detections"] += len(filtered)
        return filtered
    
    def _detect_movement(self, detections: List) -> List:
        """Detecta movimiento comparando con historial de posiciones"""
        movement_detections = []
        current_positions = defaultdict(list)
        
        for detection in detections:
            x1, y1, x2, y2, cls, cx, cy, track_id, conf = detection
            
            # Agrupar por clase para comparar posiciones
            current_positions[cls].append((cx, cy))
            
            # Verificar movimiento comparando con historial
            if self._has_significant_movement(cls, cx, cy):
                movement_detections.append(detection)
                
                if self.debug_enabled:
                    self._emit_log(f"🔧 Movimiento detectado: Track={track_id}, cls={cls}, pos=({cx:.0f},{cy:.0f})")
        
        # Actualizar historial de posiciones
        for cls, positions in current_positions.items():
            self.objetos_previos[cls] = positions[-self.max_history_length:]
        
        self.stats["movement_detections"] += len(movement_detections)
        return movement_detections
    
    def _has_significant_movement(self, cls: int, cx: float, cy: float) -> bool:
        """Verifica si hay movimiento significativo comparando con historial"""
        if cls not in self.objetos_previos or not self.objetos_previos[cls]:
            return True  # Primera detección de esta clase
        
        # Verificar distancia con todas las posiciones previas
        for prev_cx, prev_cy in self.objetos_previos[cls]:
            distance = ((cx - prev_cx) ** 2 + (cy - prev_cy) ** 2) ** 0.5
            if distance <= self.umbral_movimiento:
                return False  # Muy cerca de una posición previa
        
        return True  # Suficientemente lejos de todas las posiciones previas
    
    def _process_cell_mapping(self, detections: List) -> List:
        """Mapea detecciones a celdas y activa triggers PTZ"""
        processed_detections = []
        
        if not self.current_frame_size:
            return detections
        
        # Calcular dimensiones de celda
        cell_w = self.current_frame_size.width() / self.cell_manager.columnas
        cell_h = self.current_frame_size.height() / self.cell_manager.filas
        
        if cell_w <= 0 or cell_h <= 0:
            return detections
        
        for detection in detections:
            x1, y1, x2, y2, cls, cx, cy, track_id, conf = detection
            
            # Calcular celda correspondiente
            col = int(cx / cell_w)
            row = int(cy / cell_h)
            
            # Asegurar que esté dentro de límites
            col = max(0, min(col, self.cell_manager.columnas - 1))
            row = max(0, min(row, self.cell_manager.filas - 1))
            
            # Verificar si la celda está descartada
            if self.cell_manager.is_cell_discarded(row, col):
                if self.debug_enabled:
                    self._emit_log(f"🔶 Track {track_id} ignorado - celda descartada ({row},{col})")
                continue
            
            # Verificar cooldown de detección para esta celda
            cell_key = (row, col)
            if not self._check_detection_cooldown(cell_key):
                continue
            
            # Agregar información de celda a la detección
            detection_with_cell = detection + (row, col)
            processed_detections.append(detection_with_cell)
            
            # Marcar celda como temporal (actividad reciente)
            self.cell_manager.set_temporal_cell(row, col, True)
            
            # Emitir señal de movimiento detectado
            detection_info = {
                "track_id": track_id,
                "class": cls,
                "confidence": conf,
                "position": (cx, cy),
                "bbox": (x1, y1, x2, y2),
                "timestamp": time.time()
            }
            self.movement_detected.emit(row, col, detection_info)
            
            # Activar PTZ si está configurado para esta celda
            self._trigger_ptz_for_cell(row, col, detection_info)
            
            if self.debug_enabled:
                class_name = self._get_class_name(cls)
                self._emit_log(f"✅ {class_name} procesada: Track={track_id}, Celda=({row},{col}), Conf={conf:.2f}")
        
        return processed_detections
    
    def _check_detection_cooldown(self, cell_key: Tuple[int, int]) -> bool:
        """Verifica el cooldown de detección para una celda"""
        current_time = time.time()
        last_time = self.last_detection_time.get(cell_key, 0)
        
        if current_time - last_time >= self.detection_cooldown:
            self.last_detection_time[cell_key] = current_time
            return True
        
        return False
    
    def _trigger_ptz_for_cell(self, row: int, col: int, detection_info: Dict):
        """Activa PTZ si está configurado para la celda"""
        ptz_mapping = self.cell_manager.get_cell_ptz_mapping(row, col)
        if not ptz_mapping:
            return
        
        ip = ptz_mapping.get("ip")
        if not ip:
            return
        
        # Activar trigger automático en PTZ Manager
        success = self.ptz_manager.trigger_automatic_move(
            ip=ip,
            config=ptz_mapping,
            cell_coords=(row, col)
        )
        
        if success:
            self.stats["ptz_triggers"] += 1
            self.ptz_triggered.emit(ip, ptz_mapping, (row, col))
            
            if self.debug_enabled:
                self._emit_log(f"🎯 PTZ activado: {ip} → Celda ({row},{col})")
    
    # === UTILIDADES ===
    
    def _get_class_name(self, cls: int) -> str:
        """Convierte número de clase a nombre legible"""
        class_names = {
            0: "Persona",
            1: "Embarcación", 
            2: "Auto",
            8: "Barco",
            9: "Barco"
        }
        return class_names.get(cls, f"Clase {cls}")
    
    def _log_processing_summary(self, original_detections: List, processed_detections: List):
        """Log resumen del procesamiento (modo debug)"""
        self._emit_log(
            f"📊 Procesamiento: {len(original_detections)} → "
            f"{len(processed_detections)} detecciones finales"
        )
    
    # === GESTIÓN DE ALERTAS ===
    
    def generate_alert(self, detection_info: Dict, cell_coords: Tuple[int, int]):
        """Genera una alerta basada en una detección"""
        alert = {
            "timestamp": time.time(),
            "detection": detection_info,
            "cell": cell_coords,
            "alert_id": f"alert_{int(time.time()*1000)}_{detection_info.get('track_id', 'unknown')}",
            "severity": self._calculate_alert_severity(detection_info),
            "description": self._generate_alert_description(detection_info, cell_coords)
        }
        
        self.alert_generated.emit(alert)
        return alert
    
    def _calculate_alert_severity(self, detection_info: Dict) -> str:
        """Calcula la severidad de una alerta"""
        confidence = detection_info.get("confidence", 0)
        
        if confidence >= 0.9:
            return "high"
        elif confidence >= 0.7:
            return "medium"
        else:
            return "low"
    
    def _generate_alert_description(self, detection_info: Dict, cell_coords: Tuple[int, int]) -> str:
        """Genera descripción de la alerta"""
        class_name = self._get_class_name(detection_info.get("class", 0))
        track_id = detection_info.get("track_id", "unknown")
        confidence = detection_info.get("confidence", 0)
        row, col = cell_coords
        
        return f"{class_name} detectada en celda ({row},{col}) con {confidence*100:.0f}% confianza (Track: {track_id})"
    
    # === LIMPIEZA Y MANTENIMIENTO ===
    
    def cleanup_temporal_cells(self, max_age: float = 5.0):
        """Limpia celdas temporales antiguas"""
        current_time = time.time()
        cells_to_clear = []
        
        for (row, col) in self.cell_manager.temporal_cells:
            cell_key = (row, col)
            last_detection = self.last_detection_time.get(cell_key, 0)
            
            if current_time - last_detection > max_age:
                cells_to_clear.append((row, col))
        
        for row, col in cells_to_clear:
            self.cell_manager.set_temporal_cell(row, col, False)
        
        if cells_to_clear and self.debug_enabled:
            self._emit_log(f"🧹 Limpiadas {len(cells_to_clear)} celdas temporales")
    
    def cleanup_old_history(self, max_age: float = 30.0):
        """Limpia historial antiguo de objetos"""
        # El historial se mantiene por número de elementos, no por tiempo
        # Pero podemos limpiar clases sin actividad reciente
        current_time = time.time()
        classes_to_remove = []
        
        for cls in list(self.objetos_previos.keys()):
            if not self.objetos_previos[cls]:  # Lista vacía
                classes_to_remove.append(cls)
        
        for cls in classes_to_remove:
            del self.objetos_previos[cls]
    
    def reset_statistics(self):
        """Resetea las estadísticas"""
        self.stats = {
            "total_detections": 0,
            "filtered_detections": 0,
            "movement_detections": 0,
            "ptz_triggers": 0,
            "last_reset": time.time()
        }
        self._emit_log("📊 Estadísticas de detección reseteadas")
    
    # === CONSULTAS Y ESTADÍSTICAS ===
    
    def get_statistics(self) -> Dict[str, Any]:
        """Obtiene estadísticas del procesamiento"""
        current_time = time.time()
        uptime = current_time - self.stats["last_reset"]
        
        stats = self.stats.copy()
        stats.update({
            "uptime": uptime,
            "detection_rate": self.stats["total_detections"] / max(uptime, 1) * 60,  # por minuto
            "filter_ratio": self.stats["filtered_detections"] / max(self.stats["total_detections"], 1),
            "movement_ratio": self.stats["movement_detections"] / max(self.stats["filtered_detections"], 1),
            "ptz_trigger_ratio": self.stats["ptz_triggers"] / max(self.stats["movement_detections"], 1),
            "active_cells": len(self.cell_manager.temporal_cells),
            "tracked_classes": len(self.objetos_previos),
            "recent_detections": len([t for t in self.last_detection_time.values() 
                                    if current_time - t < 60])
        })
        
        return stats
    
    def get_configuration(self) -> Dict[str, Any]:
        """Obtiene la configuración actual"""
        return {
            "movement_threshold": self.umbral_movimiento,
            "confidence_threshold": self.confidence_threshold,
            "min_object_size": self.min_object_size,
            "max_detections_per_frame": self.max_detections_per_frame,
            "detection_cooldown": self.detection_cooldown,
            "max_history_length": self.max_history_length,
            "debug_enabled": self.debug_enabled
        }
    
    def apply_configuration(self, config: Dict[str, Any]):
        """Aplica una configuración"""
        if "movement_threshold" in config:
            self.set_movement_threshold(config["movement_threshold"])
        if "confidence_threshold" in config:
            self.set_confidence_threshold(config["confidence_threshold"])
        if "min_object_size" in config:
            self.set_min_object_size(config["min_object_size"])
        if "detection_cooldown" in config:
            self.set_detection_cooldown(config["detection_cooldown"])
        if "debug_enabled" in config:
            self.enable_debug(config["debug_enabled"])
        
        self._emit_log("⚙️ Configuración de detección aplicada")
    
    # === MÉTODOS DE COMPATIBILIDAD ===
    
    def process_legacy_detections(self, detections: List, cam_data: Dict = None) -> List:
        """Procesa detecciones en formato legacy para compatibilidad"""
        # Convertir formato legacy si es necesario
        converted_detections = []
        
        for detection in detections:
            if len(detection) >= 7:  # Formato mínimo esperado
                converted_detections.append(detection)
        
        return self.process_detections(converted_detections)
    
    def get_legacy_format_detections(self, processed_detections: List) -> List:
        """Convierte detecciones procesadas a formato legacy"""
        return [detection[:9] for detection in processed_detections]  # Remover info de celda