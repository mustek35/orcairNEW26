# gui/grilla_widget.py - VERSIÓN CORREGIDA
"""
Versión corregida con todos los métodos de compatibilidad necesarios
"""

from PyQt6.QtWidgets import QWidget, QSizePolicy, QMenu, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton, QMessageBox, QGroupBox, QFormLayout
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QFont, QImage
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QSizeF, QSize, QPointF, QTimer
from PyQt6.QtMultimedia import QVideoFrame, QVideoFrameFormat

# Importaciones del sistema existente (mantener compatibilidad)
from gui.visualizador_detector import VisualizadorDetector
from core.gestor_alertas import GestorAlertas
from core.rtsp_builder import generar_rtsp
from core.analytics_processor import AnalyticsProcessor
from gui.video_saver import VideoSaverThread
from core.cross_line_counter import CrossLineCounter
from core.ptz_control import PTZCameraONVIF
from collections import defaultdict, deque
import numpy as np
from datetime import datetime
import uuid
import json
import os
import time

# Importar módulos refactorizados OPCIONALMENTE
try:
    from gui.components.cell_manager import CellManager
    CELL_MANAGER_AVAILABLE = True
except ImportError:
    CELL_MANAGER_AVAILABLE = False

try:
    from gui.components.ptz_manager import PTZManager
    PTZ_MANAGER_AVAILABLE = True
except ImportError:
    PTZ_MANAGER_AVAILABLE = False

try:
    from gui.components.detection_handler import DetectionHandler
    DETECTION_HANDLER_AVAILABLE = True
except ImportError:
    DETECTION_HANDLER_AVAILABLE = False

try:
    from gui.components.grid_renderer import GridRenderer
    GRID_RENDERER_AVAILABLE = True
except ImportError:
    GRID_RENDERER_AVAILABLE = False

try:
    from gui.components.context_menu import ContextMenuManager
    CONTEXT_MENU_AVAILABLE = True
except ImportError:
    CONTEXT_MENU_AVAILABLE = False

try:
    from gui.components.config_manager import ConfigManager
    CONFIG_MANAGER_AVAILABLE = True
except ImportError:
    CONFIG_MANAGER_AVAILABLE = False

# Sistema modular disponible si tenemos al menos CellManager
MODULAR_SYSTEM_AVAILABLE = CELL_MANAGER_AVAILABLE
if MODULAR_SYSTEM_AVAILABLE:
    print("✅ Sistema modular disponible")
else:
    print("⚠️ Sistema modular no disponible, usando legacy")

# Constantes
DEBUG_LOGS = False
CONFIG_FILE_PATH = "config.json"


class GrillaWidget(QWidget):
    """Widget de grilla con compatibilidad hacia atrás"""
    
    log_signal = pyqtSignal(str)

    def __init__(self, filas=18, columnas=22, area=None, parent=None, fps_config=None):
        super().__init__(parent)
        
        # === CONFIGURACIÓN BÁSICA ===
        self.filas = filas
        self.columnas = columnas
        self.area = area if area else [0] * (filas * columnas)
        self.temporal = set()
        self.pixmap = None
        self.last_frame = None 
        self.original_frame_size = None 
        self.latest_tracked_boxes = []
        
        # Estados de celdas (API original)
        self.selected_cells = set()
        self.discarded_cells = set()
        self.cell_presets = {}
        self.cell_ptz_map = {}
        self.ptz_objects = {}
        self.credentials_cache = {}
        self.ptz_cameras = []

        # Datos de cámara
        self.cam_data = None
        self.alertas = None
        self.objetos_previos = {}
        self.umbral_movimiento = 20
        self.detectors = None 
        self.analytics_processor = AnalyticsProcessor(self)

        # Configuración de FPS
        if fps_config is None:
            fps_config = {"visual_fps": 15, "detection_fps": 5, "ai_fps": 2}
        self.fps_config = fps_config

        # Sistema de línea de conteo
        self.cross_counter = CrossLineCounter()
        self.cross_line_enabled = False
        self.cross_line_edit_mode = False
        self._dragging_line = None
        self._temp_line_start = None
        self._last_mouse_pos = None
        
        # === INICIALIZACIÓN ===
        self.modular_system_enabled = MODULAR_SYSTEM_AVAILABLE
        if self.modular_system_enabled:
            try:
                self._initialize_modular_system()
            except Exception as e:
                print(f"❌ Error inicializando sistema modular: {e}")
                self.modular_system_enabled = False
                self._initialize_legacy_system()
        else:
            self._initialize_legacy_system()
        
        self.registrar_log("✅ GrillaWidget inicializado (modo: {})".format(
            "modular" if self.modular_system_enabled else "legacy"
        ))

    def _initialize_modular_system(self):
        """Inicializa el sistema modular"""
        # ConfigManager
        if CONFIG_MANAGER_AVAILABLE:
            self.config_manager = ConfigManager(parent=self)
        
        # CellManager
        if CELL_MANAGER_AVAILABLE:
            self.cell_manager = CellManager(self.filas, self.columnas, parent=self)
            self._migrate_cell_states_to_modular()
        
        # PTZManager
        if PTZ_MANAGER_AVAILABLE:
            self.ptz_manager = PTZManager(parent=self)
        
        # DetectionHandler
        if (DETECTION_HANDLER_AVAILABLE and 
            hasattr(self, 'cell_manager') and 
            hasattr(self, 'ptz_manager')):
            self.detection_handler = DetectionHandler(
                self.cell_manager, 
                self.ptz_manager, 
                parent=self
            )
        
        # GridRenderer
        if GRID_RENDERER_AVAILABLE and hasattr(self, 'cell_manager'):
            self.grid_renderer = GridRenderer(self.cell_manager, parent=self)
        
        # ContextMenuManager
        if (CONTEXT_MENU_AVAILABLE and 
            hasattr(self, 'cell_manager') and 
            hasattr(self, 'ptz_manager')):
            self.context_menu = ContextMenuManager(
                self.cell_manager, 
                self.ptz_manager, 
                parent=self
            )
        
        self._connect_modular_signals()
        self._load_modular_configuration()

    def _initialize_legacy_system(self):
        """Inicializa el sistema legacy"""
        self._load_ptz_cameras_legacy()

    def _migrate_cell_states_to_modular(self):
        """Migra estados de celdas al sistema modular"""
        if not hasattr(self, 'cell_manager'):
            return
            
        # Migrar estados básicos
        self.cell_manager.selected_cells = self.selected_cells.copy()
        self.cell_manager.discarded_cells = self.discarded_cells.copy()
        self.cell_manager.cell_presets = self.cell_presets.copy()
        self.cell_manager.cell_ptz_map = self.cell_ptz_map.copy()
        self.cell_manager.area = self.area.copy()

    def _connect_modular_signals(self):
        """Conecta señales del sistema modular"""
        if hasattr(self, 'config_manager'):
            self.config_manager.log_message.connect(self.registrar_log)
        
        if hasattr(self, 'cell_manager'):
            self.cell_manager.cells_changed.connect(self._sync_legacy_cell_states)
        
        if hasattr(self, 'ptz_manager'):
            self.ptz_manager.log_message.connect(self.registrar_log)
        
        if hasattr(self, 'detection_handler'):
            self.detection_handler.log_message.connect(self.registrar_log)

    def _sync_legacy_cell_states(self):
        """Sincroniza estados modular con legacy"""
        if not hasattr(self, 'cell_manager'):
            return
            
        self.selected_cells = self.cell_manager.selected_cells.copy()
        self.discarded_cells = self.cell_manager.discarded_cells.copy()
        self.cell_presets = self.cell_manager.cell_presets.copy()
        self.cell_ptz_map = self.cell_manager.cell_ptz_map.copy()
        self.area = self.cell_manager.area.copy()
        self.update()

    def _load_modular_configuration(self):
        """Carga configuración modular"""
        if hasattr(self, 'config_manager'):
            try:
                config = self.config_manager.load_configuration()
                if hasattr(self, 'cell_manager'):
                    self.config_manager.load_grid_state(self.cell_manager)
                    self._sync_legacy_cell_states()
            except Exception as e:
                self.registrar_log(f"❌ Error cargando configuración modular: {e}")

    def _load_ptz_cameras_legacy(self):
        """Carga cámaras PTZ legacy"""
        try:
            with open(CONFIG_FILE_PATH, 'r') as f:
                config_data = json.load(f)
            
            self.ptz_cameras.clear()
            camaras_config = config_data.get("camaras", [])
            
            for cam_config in camaras_config:
                ip = cam_config.get("ip")
                tipo = cam_config.get("tipo")
                
                if tipo == "ptz" and ip and ip not in self.ptz_cameras:
                    self.ptz_cameras.append(ip)
                    self.credentials_cache[ip] = {
                        "usuario": cam_config.get("usuario", "admin"),
                        "contrasena": cam_config.get("contrasena", ""),
                        "puerto": cam_config.get("puerto", 80),
                        "tipo": tipo
                    }
            
        except Exception as e:
            self.registrar_log(f"❌ Error cargando PTZ legacy: {e}")

    # === MÉTODOS DE INTERFAZ ===

    def paintEvent(self, event):
        """Evento de pintado"""
        if (self.modular_system_enabled and 
            hasattr(self, 'grid_renderer') and 
            hasattr(self.grid_renderer, 'paint_grid')):
            # Usar sistema modular
            painter = QPainter(self)
            self.grid_renderer.paint_grid(painter, QRectF(self.rect()), self.pixmap)
        else:
            # Usar sistema legacy
            self._paint_event_legacy(event)

    def _paint_event_legacy(self, event):
        """Método de pintado legacy"""
        qp = QPainter(self)
        
        if not self.pixmap or self.pixmap.isNull():
            qp.fillRect(self.rect(), QColor("black"))
            qp.setPen(QColor("white"))
            qp.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Sin señal")
            return

        # Dibujar video
        widget_rect = QRectF(self.rect())
        pixmap_size = QSizeF(self.pixmap.size())
        scaled_size = pixmap_size.scaled(widget_rect.size(), Qt.AspectRatioMode.KeepAspectRatio)
        
        video_rect = QRectF()
        video_rect.setSize(scaled_size)
        video_rect.moveCenter(widget_rect.center())
        qp.drawPixmap(video_rect, self.pixmap, QRectF(self.pixmap.rect()))

        # Dibujar grilla
        cell_w = self.width() / self.columnas
        cell_h = self.height() / self.filas
        
        for row in range(self.filas):
            for col in range(self.columnas):
                self._paint_cell_legacy(qp, row, col, cell_w, cell_h)

        self._paint_grid_lines_legacy(qp, cell_w, cell_h)

    def _paint_cell_legacy(self, painter, row, col, cell_w, cell_h):
        """Pinta celda legacy"""
        cell_tuple = (row, col)
        brush_color = None

        if cell_tuple in self.discarded_cells:
            brush_color = QColor(200, 0, 0, 150)
        elif cell_tuple in self.cell_presets:
            brush_color = QColor(0, 0, 255, 80)
        elif cell_tuple in self.cell_ptz_map:
            brush_color = QColor(128, 0, 128, 80)
        elif cell_tuple in self.selected_cells:
            brush_color = QColor(255, 0, 0, 100)
        elif cell_tuple in self.temporal:
            brush_color = QColor(0, 255, 0, 100)
        else:
            index = row * self.columnas + col
            if index < len(self.area) and self.area[index] == 1:
                brush_color = QColor(255, 165, 0, 100)

        if brush_color is not None:
            rect_to_draw = QRectF(col * cell_w, row * cell_h, cell_w, cell_h)
            painter.fillRect(rect_to_draw, brush_color)
        
        # Mostrar preset
        if (row, col) in self.cell_presets:
            painter.setPen(QColor("white"))
            preset_text = f"P{self.cell_presets[(row, col)]}"
            painter.drawText(QPointF(col * cell_w + 2, row * cell_h + 12), preset_text)

    def _paint_grid_lines_legacy(self, painter, cell_w, cell_h):
        """Pinta líneas de grilla legacy"""
        painter.setPen(QPen(QColor(80, 80, 80, 120), 1))
        
        for col in range(self.columnas + 1):
            x = col * cell_w
            painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        
        for row in range(self.filas + 1):
            y = row * cell_h
            painter.drawLine(QPointF(0, y), QPointF(self.width(), y))

    def mousePressEvent(self, event):
        """Manejo de clics"""
        if self.cross_line_edit_mode:
            self._handle_cross_line_mouse_press(event)
            return
        
        pos = event.position()
        cell_w = self.width() / self.columnas
        cell_h = self.height() / self.filas

        if cell_w == 0 or cell_h == 0:
            return

        col = int(pos.x() / cell_w)
        row = int(pos.y() / cell_h)

        if not (0 <= row < self.filas and 0 <= col < self.columnas):
            return

        clicked_cell = (row, col)

        if event.button() == Qt.MouseButton.LeftButton:
            if self.modular_system_enabled and hasattr(self, 'cell_manager'):
                self.cell_manager.toggle_cell_selection(row, col)
            else:
                if clicked_cell in self.selected_cells:
                    self.selected_cells.remove(clicked_cell)
                else:
                    self.selected_cells.add(clicked_cell)
            self.update()
            
        elif event.button() == Qt.MouseButton.RightButton:
            menu = self._create_context_menu_legacy()
            menu.exec(event.globalPosition().toPoint())

    def _create_context_menu_legacy(self):
        """Crea menú contextual legacy"""
        menu = QMenu(self)
        
        if self.selected_cells:
            menu.addAction("Descartar celdas").triggered.connect(self._handle_discard_cells_legacy)
            menu.addAction("Habilitar celdas").triggered.connect(self._handle_enable_cells_legacy)
            menu.addAction("Asignar preset").triggered.connect(self._handle_set_preset_legacy)
            menu.addAction("Quitar preset").triggered.connect(self._handle_clear_preset_legacy)
        
        return menu

    def _handle_discard_cells_legacy(self):
        """Maneja descarte de celdas legacy"""
        self.discarded_cells.update(self.selected_cells)
        self.selected_cells.clear()
        self.update()

    def _handle_enable_cells_legacy(self):
        """Maneja habilitación de celdas legacy"""
        for cell in list(self.selected_cells):
            self.discarded_cells.discard(cell)
        self.update()

    def _handle_set_preset_legacy(self):
        """Maneja asignación de preset legacy"""
        pass  # Implementación simplificada

    def _handle_clear_preset_legacy(self):
        """Maneja limpieza de preset legacy"""
        pass  # Implementación simplificada

    def _handle_cross_line_mouse_press(self, event):
        """Maneja edición de línea de conteo"""
        pos = event.position()
        
        if event.button() == Qt.MouseButton.LeftButton:
            x_rel = pos.x() / self.width()
            y_rel = pos.y() / self.height()
            
            if not self.cross_counter.line:
                self._dragging_line = 'new'
                self._temp_line_start = pos
                self.cross_counter.set_line(((x_rel, y_rel), (x_rel, y_rel)))
            
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            self.finish_line_edit()

    # === MÉTODOS DE COMPATIBILIDAD ===

    def mostrar_vista(self, camera_data):
        """Muestra vista de cámara (MÉTODO REQUERIDO POR SISTEMA EXISTENTE)"""
        self.cam_data = camera_data
        self.registrar_log(f"📷 Vista configurada para cámara: {camera_data.get('ip', 'unknown')}")
        
        # Si tenemos sistema modular, actualizar configuración
        if (self.modular_system_enabled and 
            hasattr(self, 'detection_handler') and
            hasattr(self.detection_handler, 'apply_configuration')):
            if "modelos" in camera_data:
                detection_config = {"camera_models": camera_data["modelos"]}
                self.detection_handler.apply_configuration(detection_config)

    def actualizar_frame(self, pixmap):
        """Actualiza frame de video"""
        self.pixmap = pixmap
        if not pixmap.isNull():
            self.last_frame = pixmap.toImage()
            self.original_frame_size = QSize(pixmap.width(), pixmap.height())
            
            if (self.modular_system_enabled and 
                hasattr(self, 'detection_handler') and
                hasattr(self.detection_handler, 'set_frame_context')):
                self.detection_handler.set_frame_context(self.original_frame_size)
        
        self.update()

    def actualizar_frame_video(self, video_frame: QVideoFrame):
        """Actualiza frame desde QVideoFrame"""
        if video_frame.isValid():
            image = video_frame.toImage()
            if not image.isNull():
                pixmap = QPixmap.fromImage(image)
                self.actualizar_frame(pixmap)

    def procesar_detecciones(self, detecciones):
        """Procesa detecciones"""
        if not detecciones:
            return []
        
        if (self.modular_system_enabled and 
            hasattr(self, 'detection_handler') and
            hasattr(self.detection_handler, 'process_detections')):
            return self.detection_handler.process_detections(detecciones, self.original_frame_size)
        else:
            return self._process_detections_legacy(detecciones)

    def _process_detections_legacy(self, detecciones):
        """Procesa detecciones legacy"""
        processed = []
        for detection in detecciones:
            if len(detection) >= 9:
                x1, y1, x2, y2, cls, cx, cy, track_id, conf = detection[:9]
                if self._has_movement_legacy(cls, cx, cy):
                    processed.append(detection)
                    if self.original_frame_size:
                        cell_coords = self._get_cell_from_position(cx, cy)
                        if cell_coords:
                            self._trigger_ptz_move_legacy(*cell_coords)
        return processed

    def _has_movement_legacy(self, cls, cx, cy):
        """Detecta movimiento legacy"""
        if cls not in self.objetos_previos:
            self.objetos_previos[cls] = []
        
        for prev_cx, prev_cy in self.objetos_previos[cls]:
            distance = ((cx - prev_cx) ** 2 + (cy - prev_cy) ** 2) ** 0.5
            if distance <= self.umbral_movimiento:
                return False
        
        self.objetos_previos[cls].append((cx, cy))
        self.objetos_previos[cls] = self.objetos_previos[cls][-10:]
        return True

    def _get_cell_from_position(self, cx, cy):
        """Obtiene celda desde posición"""
        if not self.original_frame_size:
            return None
        
        cell_w = self.original_frame_size.width() / self.columnas
        cell_h = self.original_frame_size.height() / self.filas
        
        if cell_w <= 0 or cell_h <= 0:
            return None
        
        col = max(0, min(int(cx / cell_w), self.columnas - 1))
        row = max(0, min(int(cy / cell_h), self.filas - 1))
        return (row, col)

    def _trigger_ptz_move_legacy(self, row, col):
        """Activa PTZ legacy"""
        cell_key = (row, col)
        if cell_key not in self.cell_ptz_map:
            return
        
        mapping = self.cell_ptz_map[cell_key]
        ip = mapping.get("ip")
        preset = mapping.get("preset")
        
        if not ip or not preset:
            return
        
        cred = self.credentials_cache.get(ip)
        if not cred:
            return
        
        key = f"{ip}:{cred['puerto']}"
        if key not in self.ptz_objects:
            try:
                self.ptz_objects[key] = PTZCameraONVIF(
                    ip, cred['puerto'], cred['usuario'], cred['contrasena']
                )
            except Exception as e:
                self.registrar_log(f"❌ Error PTZ {ip}: {e}")
                return

        try:
            self.ptz_objects[key].goto_preset(preset)
            self.registrar_log(f"✅ PTZ {ip} → preset {preset}")
        except Exception as e:
            self.registrar_log(f"❌ Error moviendo PTZ: {e}")

    def set_camera_data(self, cam_data):
        """Establece datos de cámara"""
        self.mostrar_vista(cam_data)

    def detener(self):
        """Detiene el widget"""
        if hasattr(self, 'config_manager') and hasattr(self.config_manager, 'save_configuration'):
            try:
                self.save_configuration()
            except:
                pass

    def get_original_frame_size(self):
        """Obtiene tamaño original del frame"""
        return self.original_frame_size

    def get_latest_tracked_boxes(self):
        """Obtiene últimas cajas de tracking"""
        return self.latest_tracked_boxes

    def set_latest_tracked_boxes(self, boxes):
        """Establece cajas de tracking"""
        self.latest_tracked_boxes = boxes
        self.temporal.clear()
        for box in boxes:
            if len(box) >= 7:
                cx, cy = box[5], box[6]
                cell_coords = self._get_cell_from_position(cx, cy)
                if cell_coords:
                    self.temporal.add(cell_coords)
        self.update()

    def set_alertas_manager(self, alertas_manager):
        """Establece gestor de alertas"""
        self.alertas = alertas_manager

    def set_detectors(self, detectors):
        """Establece detectores"""
        self.detectors = detectors

    def registrar_log(self, mensaje):
        """Registra mensaje de log"""
        self.log_signal.emit(mensaje)

    def request_paint_update(self):
        """Solicita actualización de pintado"""
        self.update()

    def start_line_edit(self):
        """Inicia edición de línea"""
        self.cross_line_edit_mode = True
        self.setCursor(Qt.CursorShape.CrossCursor)

    def finish_line_edit(self):
        """Finaliza edición de línea"""
        self.cross_line_edit_mode = False
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def disable_cross_line(self):
        """Deshabilita línea de conteo"""
        self.cross_line_enabled = False
        self.cross_line_edit_mode = False
        self.cross_counter.set_line(None)
        self.update()

    def save_configuration(self):
        """Guarda configuración"""
        if (self.modular_system_enabled and 
            hasattr(self, 'config_manager') and
            hasattr(self.config_manager, 'save_configuration')):
            if hasattr(self, 'cell_manager'):
                self.config_manager.save_grid_state(self.cell_manager)
            self.config_manager.save_configuration()
        else:
            # Guardado legacy simplificado
            try:
                config_data = {
                    "selected_cells": list(self.selected_cells),
                    "discarded_cells": list(self.discarded_cells),
                    "cell_presets": self.cell_presets,
                    "cell_ptz_map": self.cell_ptz_map
                }
                with open("grilla_config_legacy.json", 'w') as f:
                    json.dump(config_data, f, indent=2)
            except Exception as e:
                self.registrar_log(f"❌ Error guardando: {e}")

    def show_asistente_rapido_ptz(self):
        """Muestra asistente rápido PTZ"""
        if self.modular_system_enabled:
            try:
                from gui.components.asistente_rapido import AsistenteRapidoPTZ
                asistente = AsistenteRapidoPTZ(self)
                asistente.show_asistente_rapido()
            except ImportError:
                self.registrar_log("❌ Asistente no disponible")
        else:
            QMessageBox.information(self, "Sistema Modular Requerido", 
                                  "El Asistente Rápido PTZ requiere el sistema modular.")

    def get_system_info(self):
        """Obtiene información del sistema"""
        return {
            "modular_enabled": self.modular_system_enabled,
            "total_cells": self.filas * self.columnas,
            "selected_cells": len(self.selected_cells),
            "ptz_cameras": len(self.ptz_cameras)
        }