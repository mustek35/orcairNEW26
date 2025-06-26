# ui/enhanced_ptz_multi_object_dialog.py - VERSIÓN CORREGIDA COMPLETA
"""
Diálogo PTZ mejorado con seguimiento multi-objeto y zoom inteligente - VERSIÓN CORREGIDA
Interfaz completa para control avanzado de cámaras PTZ con capacidades:
- Seguimiento de múltiples objetos con alternancia
- Zoom automático inteligente  
- Configuración de prioridades
- Monitoreo en tiempo real
- Estadísticas y análisis

CORRECCIÓN APLICADA: Solucionado error 'NoneType' object has no attribute 'get'
CORRECCIÓN APLICADA: Método de seguimiento no encontrado en tracker
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QComboBox, QLabel,
    QMessageBox, QGroupBox, QCheckBox, QSpinBox, QTextEdit, QSlider, QProgressBar,
    QDoubleSpinBox, QTabWidget, QWidget, QFormLayout, QSplitter, QListWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QScrollArea,
    QLineEdit, QFileDialog, QApplication
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot
from PyQt6.QtGui import QFont, QColor, QPalette, QPixmap, QPainter, QBrush
from collections import deque
import time
import json
import os
import sys
from typing import Optional, Dict, List, Any
from datetime import datetime

# Importar sistema multi-objeto
try:
    from core.multi_object_ptz_system import (
        MultiObjectPTZTracker, MultiObjectConfig, TrackingMode, ObjectPriority,
        create_multi_object_tracker, get_preset_config, PRESET_CONFIGS,
        analyze_tracking_performance
    )
    MULTI_OBJECT_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Sistema multi-objeto no disponible: {e}")
    MULTI_OBJECT_AVAILABLE = False

# Importar sistema de integración
try:
    from core.ptz_tracking_integration_enhanced import (
        PTZTrackingSystemEnhanced, start_ptz_session, stop_ptz_session,
        update_ptz_detections, process_ptz_yolo_results, get_ptz_status
    )
    INTEGRATION_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Sistema de integración no disponible: {e}")
    INTEGRATION_AVAILABLE = False

# Importar sistema básico como fallback
try:
    from core.ptz_control import PTZCameraONVIF
    BASIC_PTZ_AVAILABLE = True
except ImportError:
    BASIC_PTZ_AVAILABLE = False

# === CLASE STATUSUPDATETHREAD CORREGIDA ===
class StatusUpdateThread(QThread):
    """Hilo CORREGIDO para actualizar estado del sistema PTZ"""
    status_updated = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, tracker=None):
        super().__init__()
        self.tracker = tracker
        self.running = True
        self.error_count = 0
        self.max_errors = 10  # Máximo errores antes de detener
        
    def run(self):
        """Ejecutar actualizaciones de estado con manejo de errores mejorado"""
        while self.running:
            try:
                if not self.tracker:
                    time.sleep(1.0)
                    continue
                
                # Obtener estado de forma segura
                status = self._get_safe_status()
                
                if status and isinstance(status, dict):
                    self.error_count = 0  # Reset contador en éxito
                    self.status_updated.emit(status)
                else:
                    self.error_count += 1
                    self.error_occurred.emit(f"Estado inválido (error #{self.error_count})")
                
                # Si hay demasiados errores, detener hilo
                if self.error_count >= self.max_errors:
                    self.error_occurred.emit("Demasiados errores consecutivos, deteniendo hilo")
                    break
                
                # Esperar más tiempo si hay errores
                time.sleep(1.0 if self.error_count > 0 else 0.5)
                
            except Exception as e:
                self.error_count += 1
                self.error_occurred.emit(f"Error en hilo de estado: {e}")
                
                if self.error_count >= self.max_errors:
                    self.error_occurred.emit("Demasiados errores consecutivos, deteniendo hilo")
                    break
                
                time.sleep(1.0)
    
    def _get_safe_status(self) -> Optional[Dict[str, Any]]:
        """Obtener estado del tracker de forma segura"""
        try:
            # Verificar que el tracker tiene método get_status
            if not hasattr(self.tracker, 'get_status'):
                return self._create_default_status("Tracker sin método get_status")
            
            # Intentar obtener estado
            status = self.tracker.get_status()
            
            # Verificar que el estado es válido
            if status is None:
                return self._create_default_status("Estado None retornado")
            
            # Verificar que es un diccionario
            if not isinstance(status, dict):
                return self._create_default_status(f"Estado inválido: {type(status)}")
            
            # Asegurar campos mínimos requeridos
            safe_status = self._ensure_required_fields(status)
            return safe_status
            
        except Exception as e:
            return self._create_default_status(f"Error: {e}")
    
    def _ensure_required_fields(self, status: Dict[str, Any]) -> Dict[str, Any]:
        """Asegurar que el estado tiene todos los campos requeridos"""
        safe_status = {
            # Campos básicos con valores por defecto
            'connected': status.get('connected', False),
            'tracking_active': status.get('tracking_active', False),
            'successful_moves': status.get('successful_moves', 0),
            'failed_moves': status.get('failed_moves', 0),
            'total_detections': status.get('total_detections', 0),
            'success_rate': status.get('success_rate', 0.0),
            'ip': status.get('ip', 'unknown'),
            'active_objects': status.get('active_objects', 0),
            'current_target': status.get('current_target', None),
            'camera_ip': status.get('camera_ip', status.get('ip', 'unknown')),
            'session_time': status.get('session_time', 0),
            'switches_count': status.get('switches_count', 0),
            'last_update': time.time()
        }
        return safe_status
    
    def _create_default_status(self, reason="Estado no disponible"):
        """Crear estado por defecto cuando no se puede obtener del tracker"""
        return {
            'connected': False,
            'tracking_active': False,
            'successful_moves': 0,
            'failed_moves': 0,
            'total_detections': 0,
            'success_rate': 0.0,
            'ip': 'unknown',
            'active_objects': 0,
            'current_target': None,
            'camera_ip': 'unknown',
            'session_time': 0,
            'switches_count': 0,
            'status_error': reason,
            'last_update': time.time()
        }
    
    def stop(self):
        """Detener el hilo de forma segura"""
        self.running = False

class EnhancedMultiObjectPTZDialog(QDialog):
    """Diálogo principal para control PTZ multi-objeto"""
    
    # Señales para comunicación
    tracking_started = pyqtSignal()
    tracking_stopped = pyqtSignal()
    object_detected = pyqtSignal(int, dict)
    object_lost = pyqtSignal(int)
    target_switched = pyqtSignal(int, int)
    zoom_changed = pyqtSignal(float, float)
    tracking_stats_updated = pyqtSignal(dict)
    
    def __init__(self, parent=None, camera_list=None):
        super().__init__(parent)
        self.setWindowTitle("🎯 Control PTZ Multi-Objeto Avanzado")
        self.setMinimumSize(900, 700)
        
        # Verificar disponibilidad de sistemas
        if not MULTI_OBJECT_AVAILABLE and not INTEGRATION_AVAILABLE:
            self._show_error_dialog()
            return
        
        # Datos del sistema
        self.all_cameras = camera_list or []
        self.current_camera_data = None
        self.tracking_active = False
        self.current_camera_id = None
        
        # Sistema PTZ
        self.current_tracker = None
        self.status_thread = None
        
        # Configuración
        if MULTI_OBJECT_AVAILABLE:
            self.multi_config = MultiObjectConfig()
        else:
            self.multi_config = None
            
        self.config_file = "ptz_multi_object_ui_config.json"
        
        # Estadísticas
        self.detection_count = 0
        self.session_start_time = 0
        self.performance_history = []

        # Seguimiento de detecciones perdidas
        self.frames_without_detection = 0
        self.search_zoom_speed = 0.05
        self.last_known_ptz = None
        self.position_history = deque(maxlen=20)
        self.initial_zoom_level = None
        self.detection_preset = None

        # Margen de centrado antes de aplicar zoom
        self.centering_margin = 0.1
        
        # Timer para actualización de UI
        self.ui_update_timer = QTimer()
        self.ui_update_timer.timeout.connect(self._update_ui_displays)
        self.ui_update_timer.start(1000)  # Cada segundo

        # Timer único para detener movimiento PTZ
        self._stop_timer = QTimer()
        self._stop_timer.setSingleShot(True)
        self._stop_timer.timeout.connect(self._stop_current_movement)
        
        # Configurar interfaz
        self._setup_enhanced_ui()
        self._connect_all_signals()
        self._load_camera_configuration()
        self._load_ui_configuration()
        
        # Aplicar tema
        self._apply_dark_theme()
        
        self._log("🎯 Sistema PTZ Multi-Objeto inicializado")

    def closeEvent(self, event):
        """Manejar cierre del diálogo con limpieza completa de recursos"""
        print("INFO: Iniciando cierre de EnhancedMultiObjectPTZDialog...")
        
        try:
            # Detener seguimiento si está activo
            if hasattr(self, 'tracking_active') and self.tracking_active:
                self._log("🛑 Deteniendo seguimiento antes del cierre...")
                self._stop_tracking()
            
            # Detener hilo de estado
            if hasattr(self, 'status_thread') and self.status_thread:
                self.status_thread.stop()
                self.status_thread.wait(2000)  # Esperar máximo 2 segundos
                
            # Detener timer de UI
            if hasattr(self, 'ui_update_timer') and self.ui_update_timer:
                self.ui_update_timer.stop()

            # Detener timer de parada PTZ
            if hasattr(self, '_stop_timer') and self._stop_timer.isActive():
                self._stop_timer.stop()
            
            # Limpiar tracker
            if hasattr(self, 'current_tracker') and self.current_tracker:
                try:
                    if hasattr(self.current_tracker, 'cleanup'):
                        self.current_tracker.cleanup()
                    self.current_tracker = None
                    print("INFO: Tracker PTZ limpiado")
                except Exception as e:
                    print(f"WARN: Error limpiando tracker: {e}")
            
            # Guardar configuración antes del cierre
            self._save_ui_configuration()
            
            print("INFO: Cierre de EnhancedMultiObjectPTZDialog completado")
            event.accept()
            
        except Exception as e:
            print(f"ERROR: Error durante cierre: {e}")
            event.accept()  # Forzar cierre incluso con errores

    def _setup_enhanced_ui(self):
        """Configurar interfaz de usuario mejorada"""
        layout = QVBoxLayout(self)
        
        # === HEADER ===
        header_frame = QFrame()
        header_frame.setStyleSheet("QFrame { background: #2b2b2b; border-radius: 5px; padding: 10px; }")
        header_layout = QHBoxLayout(header_frame)
        
        title_label = QLabel("🎯 Control PTZ Multi-Objeto Avanzado")
        title_label.setStyleSheet("color: #ffffff; font-size: 18px; font-weight: bold;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # Status LED
        self.status_led = QLabel("●")
        self.status_led.setStyleSheet("color: #ff4444; font-size: 16px;")
        header_layout.addWidget(QLabel("Estado:"))
        header_layout.addWidget(self.status_led)
        
        layout.addWidget(header_frame)
        
        # === MAIN CONTENT ===
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Panel izquierdo - Controles
        control_widget = self._create_control_panel()
        main_splitter.addWidget(control_widget)
        
        # Panel derecho - Monitoreo
        monitor_widget = self._create_monitor_panel()
        main_splitter.addWidget(monitor_widget)
        
        main_splitter.setSizes([400, 500])
        layout.addWidget(main_splitter)

    def _create_control_panel(self):
        """Crear panel de control"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # === SELECCIÓN DE CÁMARA ===
        camera_group = QGroupBox("📹 Selección de Cámara")
        camera_layout = QFormLayout(camera_group)
        
        self.camera_combo = QComboBox()
        self.camera_combo.currentTextChanged.connect(self._on_camera_selected)
        camera_layout.addRow("Cámara PTZ:", self.camera_combo)
        
        # Info de cámara
        self.camera_info_label = QLabel("No hay cámara seleccionada")
        self.camera_info_label.setStyleSheet("color: #888888; font-size: 11px;")
        camera_layout.addRow("Info:", self.camera_info_label)
        
        layout.addWidget(camera_group)
        
        # === CONTROLES DE SEGUIMIENTO ===
        tracking_group = QGroupBox("🎯 Control de Seguimiento")
        tracking_layout = QVBoxLayout(tracking_group)
        
        # Modo de seguimiento
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Modo:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Objeto Individual", "Multi-Objeto Alternante", "Multi-Objeto Paralelo"])
        mode_layout.addWidget(self.mode_combo)
        tracking_layout.addLayout(mode_layout)
        
        # Botones principales
        buttons_layout = QHBoxLayout()
        self.start_btn = QPushButton("▶️ Iniciar Seguimiento")
        self.start_btn.clicked.connect(self._start_tracking)
        self.start_btn.setStyleSheet("QPushButton { background: #4CAF50; color: white; padding: 8px; border-radius: 4px; }")
        
        self.stop_btn = QPushButton("⏹️ Detener Seguimiento")
        self.stop_btn.clicked.connect(self._stop_tracking)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("QPushButton { background: #f44336; color: white; padding: 8px; border-radius: 4px; }")
        
        buttons_layout.addWidget(self.start_btn)
        buttons_layout.addWidget(self.stop_btn)
        tracking_layout.addLayout(buttons_layout)
        
        # Preset de posición
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("Preset:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["Ninguno", "1", "2", "3", "4", "5"])
        preset_layout.addWidget(self.preset_combo)
        
        self.goto_preset_btn = QPushButton("Ir a Preset")
        self.goto_preset_btn.clicked.connect(self._goto_preset)
        preset_layout.addWidget(self.goto_preset_btn)
        self.recover_btn = QPushButton("Recuperar Objetivo")
        self.recover_btn.clicked.connect(self._recenter_on_last_known)
        preset_layout.addWidget(self.recover_btn)
        tracking_layout.addLayout(preset_layout)
        
        layout.addWidget(tracking_group)
        
        # === CONFIGURACIÓN MULTI-OBJETO ===
        if MULTI_OBJECT_AVAILABLE:
            config_group = self._create_multi_object_config()
            layout.addWidget(config_group)
        
        # === CONFIGURACIÓN DE ZOOM ===
        zoom_group = QGroupBox("🔍 Control de Zoom")
        zoom_layout = QFormLayout(zoom_group)
        
        self.auto_zoom_cb = QCheckBox("Zoom Automático")
        self.auto_zoom_cb.setChecked(True)
        zoom_layout.addRow(self.auto_zoom_cb)
        
        self.zoom_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_speed_slider.setRange(1, 10)
        self.zoom_speed_slider.setValue(5)
        zoom_layout.addRow("Velocidad:", self.zoom_speed_slider)
        
        self.target_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.target_size_slider.setRange(10, 80)
        self.target_size_slider.setValue(30)
        zoom_layout.addRow("Tamaño objetivo (%):", self.target_size_slider)
        
        layout.addWidget(zoom_group)
        
        layout.addStretch()
        return widget

    def _create_multi_object_config(self):
        """Crear configuración multi-objeto"""
        group = QGroupBox("⚙️ Configuración Multi-Objeto")
        layout = QFormLayout(group)
        
        # Alternancia
        self.alternating_cb = QCheckBox("Alternar Objetivos")
        self.alternating_cb.setChecked(True)
        layout.addRow(self.alternating_cb)
        
        # Tiempos de seguimiento
        self.primary_time_spin = QDoubleSpinBox()
        self.primary_time_spin.setRange(1.0, 30.0)
        self.primary_time_spin.setValue(5.0)
        self.primary_time_spin.setSuffix(" s")
        layout.addRow("Tiempo primario:", self.primary_time_spin)
        
        self.secondary_time_spin = QDoubleSpinBox()
        self.secondary_time_spin.setRange(1.0, 30.0)
        self.secondary_time_spin.setValue(3.0)
        self.secondary_time_spin.setSuffix(" s")
        layout.addRow("Tiempo secundario:", self.secondary_time_spin)
        
        # Máximo de objetos
        self.max_objects_spin = QSpinBox()
        self.max_objects_spin.setRange(1, 10)
        self.max_objects_spin.setValue(3)
        layout.addRow("Máx. objetos:", self.max_objects_spin)
        
        # Confianza mínima
        self.min_conf_slider = QSlider(Qt.Orientation.Horizontal)
        self.min_conf_slider.setRange(30, 95)
        self.min_conf_slider.setValue(50)
        self.min_conf_label = QLabel("50%")
        self.min_conf_slider.valueChanged.connect(lambda v: self.min_conf_label.setText(f"{v}%"))
        
        conf_layout = QHBoxLayout()
        conf_layout.addWidget(self.min_conf_slider)
        conf_layout.addWidget(self.min_conf_label)
        layout.addRow("Confianza mín.:", conf_layout)
        
        return group

    def _create_monitor_panel(self):
        """Crear panel de monitoreo"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # === ESTADO ACTUAL ===
        status_group = QGroupBox("📊 Estado Actual")
        status_layout = QFormLayout(status_group)
        
        self.connection_label = QLabel("❌ Desconectado")
        status_layout.addRow("Conexión:", self.connection_label)
        
        self.tracking_label = QLabel("⏹️ Inactivo")
        status_layout.addRow("Seguimiento:", self.tracking_label)
        
        self.target_label = QLabel("Ninguno")
        status_layout.addRow("Objetivo actual:", self.target_label)
        
        self.objects_label = QLabel("0")
        status_layout.addRow("Objetos activos:", self.objects_label)
        
        self.detections_label = QLabel("0")
        status_layout.addRow("Detecciones:", self.detections_label)
        
        layout.addWidget(status_group)
        
        # === ESTADÍSTICAS ===
        stats_group = QGroupBox("📈 Estadísticas")
        stats_layout = QFormLayout(stats_group)
        
        self.success_rate_label = QLabel("0%")
        stats_layout.addRow("Tasa de éxito:", self.success_rate_label)
        
        self.moves_label = QLabel("0 / 0")
        stats_layout.addRow("Movimientos (✅/❌):", self.moves_label)
        
        self.switches_label = QLabel("0")
        stats_layout.addRow("Cambios de objetivo:", self.switches_label)
        
        self.session_time_label = QLabel("00:00")
        stats_layout.addRow("Tiempo de sesión:", self.session_time_label)
        
        layout.addWidget(stats_group)
        
        # === LOG DE ACTIVIDAD ===
        log_group = QGroupBox("📝 Log de Actividad")
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(200)
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("QTextEdit { background: #1e1e1e; color: #ffffff; border: 1px solid #444; }")
        log_layout.addWidget(self.log_text)
        
        # Botones de log
        log_buttons = QHBoxLayout()
        clear_log_btn = QPushButton("Limpiar Log")
        clear_log_btn.clicked.connect(self._clear_log)
        save_log_btn = QPushButton("Guardar Log")
        save_log_btn.clicked.connect(self._save_log)
        
        log_buttons.addWidget(clear_log_btn)
        log_buttons.addWidget(save_log_btn)
        log_buttons.addStretch()
        log_layout.addLayout(log_buttons)
        
        layout.addWidget(log_group)
        
        # === GRÁFICO DE RENDIMIENTO ===
        perf_group = QGroupBox("📊 Rendimiento en Tiempo Real")
        perf_layout = QVBoxLayout(perf_group)
        
        self.performance_progress = QProgressBar()
        self.performance_progress.setRange(0, 100)
        perf_layout.addWidget(QLabel("Eficiencia actual:"))
        perf_layout.addWidget(self.performance_progress)
        
        layout.addWidget(perf_group)
        
        layout.addStretch()
        return widget

    def _connect_all_signals(self):
        """Conectar todas las señales"""
        # Señales de configuración
        if hasattr(self, 'alternating_cb'):
            self.alternating_cb.toggled.connect(self._update_multi_config)
        if hasattr(self, 'primary_time_spin'):
            self.primary_time_spin.valueChanged.connect(self._update_multi_config)
        if hasattr(self, 'secondary_time_spin'):
            self.secondary_time_spin.valueChanged.connect(self._update_multi_config)
        if hasattr(self, 'max_objects_spin'):
            self.max_objects_spin.valueChanged.connect(self._update_multi_config)
        if hasattr(self, 'min_conf_slider'):
            self.min_conf_slider.valueChanged.connect(self._update_multi_config)
        
        # Señales de zoom
        self.auto_zoom_cb.toggled.connect(self._update_zoom_config)
        self.zoom_speed_slider.valueChanged.connect(self._update_zoom_config)
        self.target_size_slider.valueChanged.connect(self._update_zoom_config)

    def _load_camera_configuration(self):
        """Cargar configuración de cámaras"""
        self.camera_combo.clear()
        
        if not self.all_cameras:
            self.camera_combo.addItem("No hay cámaras PTZ disponibles")
            return
        
        for i, camera in enumerate(self.all_cameras):
            # Verificar que sea cámara PTZ
            if camera.get('tipo', '').lower() == 'ptz':
                name = camera.get('nombre', f"Cámara {i+1}")
                ip = camera.get('ip', 'Sin IP')
                self.camera_combo.addItem(f"{name} ({ip})")
        
        if self.camera_combo.count() == 0:
            self.camera_combo.addItem("No hay cámaras PTZ configuradas")

    def _load_ui_configuration(self):
        """Cargar configuración de UI"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # Aplicar configuración guardada
                if 'camera_index' in config and config['camera_index'] < self.camera_combo.count():
                    self.camera_combo.setCurrentIndex(config['camera_index'])
                
                if 'mode' in config:
                    mode_index = self.mode_combo.findText(config['mode'])
                    if mode_index >= 0:
                        self.mode_combo.setCurrentIndex(mode_index)
                
                # Configuración multi-objeto
                if MULTI_OBJECT_AVAILABLE and 'multi_object' in config:
                    mo_config = config['multi_object']
                    if hasattr(self, 'alternating_cb'):
                        self.alternating_cb.setChecked(mo_config.get('alternating', True))
                    if hasattr(self, 'primary_time_spin'):
                        self.primary_time_spin.setValue(mo_config.get('primary_time', 5.0))
                    if hasattr(self, 'secondary_time_spin'):
                        self.secondary_time_spin.setValue(mo_config.get('secondary_time', 3.0))
                    if hasattr(self, 'max_objects_spin'):
                        self.max_objects_spin.setValue(mo_config.get('max_objects', 3))
                    if hasattr(self, 'min_conf_slider'):
                        self.min_conf_slider.setValue(mo_config.get('min_confidence', 50))
                
                # Configuración de zoom
                if 'zoom' in config:
                    zoom_config = config['zoom']
                    self.auto_zoom_cb.setChecked(zoom_config.get('auto_zoom', True))
                    self.zoom_speed_slider.setValue(zoom_config.get('zoom_speed', 5))
                    self.target_size_slider.setValue(zoom_config.get('target_size', 30))
                
                self._log("📁 Configuración UI cargada")
        except Exception as e:
            self._log(f"⚠️ Error cargando configuración UI: {e}")

    def _save_ui_configuration(self):
        """Guardar configuración de UI"""
        try:
            config = {
                'camera_index': self.camera_combo.currentIndex(),
                'mode': self.mode_combo.currentText(),
                'zoom': {
                    'auto_zoom': self.auto_zoom_cb.isChecked(),
                    'zoom_speed': self.zoom_speed_slider.value(),
                    'target_size': self.target_size_slider.value()
                }
            }
            
            # Configuración multi-objeto
            if MULTI_OBJECT_AVAILABLE and hasattr(self, 'alternating_cb'):
                config['multi_object'] = {
                    'alternating': self.alternating_cb.isChecked(),
                    'primary_time': self.primary_time_spin.value(),
                    'secondary_time': self.secondary_time_spin.value(),
                    'max_objects': self.max_objects_spin.value(),
                    'min_confidence': self.min_conf_slider.value()
                }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
                
        except Exception as e:
            print(f"Error guardando configuración UI: {e}")

    def _apply_dark_theme(self):
        """Aplicar tema oscuro"""
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #555;
                border-radius: 5px;
                margin-top: 1ex;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QPushButton {
                background-color: #404040;
                border: 1px solid #555;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QPushButton:pressed {
                background-color: #353535;
            }
            QComboBox, QSpinBox, QDoubleSpinBox {
                background-color: #404040;
                border: 1px solid #555;
                padding: 3px;
                border-radius: 3px;
            }
            QSlider::groove:horizontal {
                border: 1px solid #999;
                height: 8px;
                background: #404040;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #4CAF50;
                border: 1px solid #5c5c5c;
                width: 18px;
                border-radius: 9px;
            }
            QProgressBar {
                border: 1px solid #555;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 4px;
            }
        """)

    def _on_camera_selected(self):
        """Manejar selección de cámara"""
        current_index = self.camera_combo.currentIndex()
        if current_index >= 0 and current_index < len(self.all_cameras):
            self.current_camera_data = self.all_cameras[current_index]
            self.current_camera_id = self.current_camera_data.get('ip', f'camera_{current_index}')
            
            # Actualizar info de cámara
            ip = self.current_camera_data.get('ip', 'Sin IP')
            port = self.current_camera_data.get('puerto', 80)
            user = self.current_camera_data.get('usuario', 'N/A')
            self.camera_info_label.setText(f"IP: {ip}:{port} | Usuario: {user}")
            
            self._log(f"📹 Cámara seleccionada: {self.current_camera_data.get('nombre', 'Sin nombre')} ({ip})")
        else:
            self.current_camera_data = None
            self.current_camera_id = None
            self.camera_info_label.setText("No hay cámara seleccionada")

    def _start_tracking(self):
        """Iniciar seguimiento PTZ"""
        try:
            if not self.current_camera_data:
                QMessageBox.warning(self, "Error", "Seleccione una cámara PTZ primero")
                return
            
            if self.tracking_active:
                self._log("⚠️ El seguimiento ya está activo")
                return
            
            self._log("🚀 Iniciando sistema de seguimiento PTZ...")
            
            # Crear tracker según el modo y sistemas disponibles
            success = self._create_tracker()
            if not success:
                self._log("❌ Error creando tracker PTZ")
                return
            
            # Inicializar tracker
            if hasattr(self.current_tracker, 'initialize'):
                if not self.current_tracker.initialize():
                    self._log("❌ Error inicializando tracker PTZ")
                    return
            
            # Conectar tracker si es necesario
            if hasattr(self.current_tracker, 'connect'):
                if not self.current_tracker.connect():
                    self._log("❌ Error conectando con cámara PTZ")
                    return
            
            # Iniciar seguimiento
            if hasattr(self.current_tracker, 'start_tracking'):
                if not self.current_tracker.start_tracking():
                    self._log("❌ Error iniciando seguimiento")
                    return
            
            # Actualizar estado
            self.tracking_active = True
            self.session_start_time = time.time()
            self.detection_count = 0
            
            # Actualizar UI
            self._update_tracking_ui(True)
            
            # Iniciar hilo de estado
            self._start_status_thread()
            
            self._log("✅ Seguimiento PTZ iniciado exitosamente")
            self.tracking_started.emit()
            
        except Exception as e:
            self._log(f"❌ Error iniciando seguimiento: {e}")
            QMessageBox.critical(self, "Error", f"Error iniciando seguimiento:\n{e}")

    def _stop_tracking(self):
        """Detener seguimiento PTZ"""
        try:
            if not self.tracking_active:
                self._log("⚠️ El seguimiento no está activo")
                return
            
            self._log("🛑 Deteniendo seguimiento PTZ...")
            
            # Detener hilo de estado
            if self.status_thread:
                self.status_thread.stop()
                self.status_thread.wait(2000)
                self.status_thread = None
            
            # Detener tracker
            if self.current_tracker:
                try:
                    if hasattr(self.current_tracker, 'stop_tracking'):
                        self.current_tracker.stop_tracking()
                    if hasattr(self.current_tracker, 'disconnect'):
                        self.current_tracker.disconnect()
                except Exception as e:
                    self._log(f"⚠️ Error deteniendo tracker: {e}")

                self.current_tracker = None
                self.detection_preset = None
                self.initial_zoom_level = None
            
            # Actualizar estado
            self.tracking_active = False
            
            # Actualizar UI
            self._update_tracking_ui(False)
            
            self._log("✅ Seguimiento PTZ detenido")
            self.tracking_stopped.emit()
            
        except Exception as e:
            self._log(f"❌ Error deteniendo seguimiento: {e}")

    def _create_tracker(self):
        """Crear tracker PTZ según el modo seleccionado"""
        try:
            mode = self.mode_combo.currentText()
            self._log(f"🎯 Modo de seguimiento: {mode}")
            
            # Extraer datos de conexión
            ip = self.current_camera_data.get('ip')
            port = self.current_camera_data.get('puerto', 80)
            username = self.current_camera_data.get('usuario', 'admin')
            password = self.current_camera_data.get('contrasena', 'admin')
            
            if not ip:
                self._log("❌ IP de cámara no válida")
                return False
            
            # CASO 1: Sistema Multi-Objeto Disponible
            if MULTI_OBJECT_AVAILABLE and "Multi-Objeto" in mode:
                try:
                    from core.multi_object_ptz_system import MultiObjectPTZTracker, MultiObjectConfig
                    
                    # Crear configuración multi-objeto
                    config = self._get_current_multi_config()
                    
                    # Crear tracker multi-objeto
                    self.current_tracker = MultiObjectPTZTracker(
                        ip=ip,
                        port=port,
                        username=username,
                        password=password,
                        multi_config=config
                    )
                    
                    self._log("✅ Tracker multi-objeto creado")
                    return True
                    
                except Exception as e:
                    self._log(f"❌ Error creando tracker multi-objeto: {e}")
                    # Continuar con tracker básico
            
            # CASO 2: Sistema de Integración Disponible
            if INTEGRATION_AVAILABLE:
                try:
                    from core.ptz_tracking_integration_enhanced import PTZTrackingSystemEnhanced
                    
                    # Crear sistema de integración
                    integration_system = PTZTrackingSystemEnhanced()
                    
                    # Crear sesión de cámara
                    session_id = f"camera_{ip}"
                    session_config = self._get_current_multi_config() if MULTI_OBJECT_AVAILABLE else None
                    
                    success = integration_system.start_session(
                        camera_id=session_id,
                        ip=ip,
                        port=port,
                        username=username,
                        password=password,
                        preset_token=self._get_selected_preset(),
                        config=session_config
                    )
                    
                    if success:
                        self.current_tracker = integration_system
                        self._log("✅ Sistema de integración PTZ creado")
                        return True
                    
                except Exception as e:
                    self._log(f"❌ Error creando sistema de integración: {e}")
                    # Continuar con tracker básico
            
            # CASO 3: Tracker Básico PTZ (Fallback)
            if BASIC_PTZ_AVAILABLE:
                try:
                    from core.ptz_control import PTZCameraONVIF
                    
                    self.current_tracker = PTZCameraONVIF(ip, port, username, password)
                    
                    # Agregar métodos de compatibilidad
                    self._add_basic_tracker_methods()
                    
                    self._log("✅ Tracker PTZ básico creado")
                    return True
                    
                except Exception as e:
                    self._log(f"❌ Error creando tracker básico: {e}")
                    return False
            
            # No hay sistemas disponibles
            self._log("❌ No hay sistemas PTZ disponibles")
            return False
            
        except Exception as e:
            self._log(f"❌ Error general creando tracker: {e}")
            return False

    def _add_basic_tracker_methods(self):
        """Agregar métodos de compatibilidad al tracker básico"""
        if not self.current_tracker:
            return
        
        # Agregar método get_status si no existe
        if not hasattr(self.current_tracker, 'get_status'):
            def get_status():
                return {
                    'connected': hasattr(self.current_tracker, 'ptz_service') and self.current_tracker.ptz_service is not None,
                    'tracking_active': self.tracking_active,
                    'ip': getattr(self.current_tracker, 'ip', 'unknown'),
                    'successful_moves': getattr(self.current_tracker, 'successful_moves', 0),
                    'failed_moves': getattr(self.current_tracker, 'failed_moves', 0),
                    'total_detections': self.detection_count
                }
            self.current_tracker.get_status = get_status
        
        # Agregar método connect si no existe
        if not hasattr(self.current_tracker, 'connect'):
            def connect():
                try:
                    # Ya se conecta en __init__, solo verificar
                    return hasattr(self.current_tracker, 'ptz_service') and self.current_tracker.ptz_service is not None
                except:
                    return False
            self.current_tracker.connect = connect
        
        # Agregar método start_tracking si no existe
        if not hasattr(self.current_tracker, 'start_tracking'):
            def start_tracking():
                return True  # El tracker básico no necesita inicialización especial
            self.current_tracker.start_tracking = start_tracking
        
        # Agregar método stop_tracking si no existe
        if not hasattr(self.current_tracker, 'stop_tracking'):
            def stop_tracking():
                try:
                    if hasattr(self.current_tracker, 'stop'):
                        self.current_tracker.stop()
                    return True
                except:
                    return False
            self.current_tracker.stop_tracking = stop_tracking
        
        # Inicializar contadores
        if not hasattr(self.current_tracker, 'successful_moves'):
            self.current_tracker.successful_moves = 0
        if not hasattr(self.current_tracker, 'failed_moves'):
            self.current_tracker.failed_moves = 0

    def _get_current_multi_config(self):
        """Obtener configuración multi-objeto actual"""
        if not MULTI_OBJECT_AVAILABLE or not hasattr(self, 'alternating_cb'):
            return None
        
        try:
            from core.multi_object_ptz_system import MultiObjectConfig
            
            return MultiObjectConfig(
                alternating_enabled=self.alternating_cb.isChecked(),
                primary_follow_time=self.primary_time_spin.value(),
                secondary_follow_time=self.secondary_time_spin.value(),
                max_objects_to_track=self.max_objects_spin.value(),
                min_confidence_threshold=self.min_conf_slider.value() / 100.0,
                auto_zoom_enabled=self.auto_zoom_cb.isChecked(),
                target_object_ratio=self.target_size_slider.value() / 100.0,
                zoom_speed=self.zoom_speed_slider.value() / 10.0
            )
        except Exception as e:
            self._log(f"⚠️ Error creando configuración multi-objeto: {e}")
            return None

    def _get_selected_preset(self):
        """Obtener preset seleccionado"""
        preset_text = self.preset_combo.currentText()
        if preset_text == "Ninguno":
            return None
        try:
            return str(preset_text)
        except:
            return None

    def _goto_preset(self):
        """Ir a preset seleccionado"""
        try:
            preset = self._get_selected_preset()
            if not preset:
                self._log("⚠️ No hay preset seleccionado")
                return
            
            if not self.current_tracker:
                self._log("⚠️ No hay tracker activo")
                return
            
            # Intentar ir al preset
            success = False
            if hasattr(self.current_tracker, 'goto_preset'):
                success = self.current_tracker.goto_preset(preset)
            elif hasattr(self.current_tracker, 'goto_preset_and_track'):
                success = self.current_tracker.goto_preset_and_track(preset, False)
            
            if success:
                self._log(f"✅ Movido a preset {preset}")
            else:
                self._log(f"❌ Error moviendo a preset {preset}")
                
        except Exception as e:
            self._log(f"❌ Error en goto_preset: {e}")

    def _start_status_thread(self):
        """Iniciar hilo de actualización de estado"""
        try:
            if self.status_thread:
                self.status_thread.stop()
                self.status_thread.wait(1000)
            
            if self.current_tracker:
                self.status_thread = StatusUpdateThread(self.current_tracker)
                self.status_thread.status_updated.connect(self._update_status_display)
                self.status_thread.error_occurred.connect(self._handle_status_error)
                self.status_thread.start()
                self._log("✅ Hilo de estado iniciado")
            
        except Exception as e:
            self._log(f"❌ Error iniciando hilo de estado: {e}")

    def _update_tracking_ui(self, active: bool):
        """Actualizar UI según estado de seguimiento"""
        self.start_btn.setEnabled(not active)
        self.stop_btn.setEnabled(active)
        
        if active:
            self.status_led.setStyleSheet("color: #4CAF50; font-size: 16px;")
            self.tracking_label.setText("▶️ Activo")
        else:
            self.status_led.setStyleSheet("color: #ff4444; font-size: 16px;")
            self.tracking_label.setText("⏹️ Inactivo")

    @pyqtSlot(dict)
    def _update_status_display(self, status: dict):
        """Actualizar display de estado - MÉTODO CORREGIDO"""
        try:
            if not status or not isinstance(status, dict):
                return
            
            # Actualizar conexión
            connected = status.get('connected', False)
            if connected:
                self.connection_label.setText("✅ Conectado")
            else:
                self.connection_label.setText("❌ Desconectado")
            
            # Actualizar objetivo actual
            current_target = status.get('current_target')
            if current_target:
                if isinstance(current_target, dict):
                    target_class = current_target.get('class', 'objeto')
                    confidence = current_target.get('confidence', 0)
                    self.target_label.setText(f"{target_class} (conf: {confidence:.2f})")
                else:
                    self.target_label.setText(str(current_target))
            else:
                self.target_label.setText("Ninguno")
            
            # Actualizar objetos activos
            active_objects = status.get('active_objects', 0)
            self.objects_label.setText(str(active_objects))
            
            # Actualizar detecciones
            total_detections = status.get('total_detections', 0)
            self.detections_label.setText(str(total_detections))
            
            # Actualizar estadísticas
            success_rate = status.get('success_rate', 0)
            self.success_rate_label.setText(f"{success_rate:.1f}%")
            self.performance_progress.setValue(int(success_rate))
            
            successful_moves = status.get('successful_moves', 0)
            failed_moves = status.get('failed_moves', 0)
            self.moves_label.setText(f"{successful_moves} / {failed_moves}")
            
            switches_count = status.get('switches_count', 0)
            self.switches_label.setText(str(switches_count))
            
            # Actualizar tiempo de sesión
            session_time = status.get('session_time', 0)
            if session_time == 0 and self.tracking_active:
                session_time = time.time() - self.session_start_time
            
            minutes = int(session_time // 60)
            seconds = int(session_time % 60)
            self.session_time_label.setText(f"{minutes:02d}:{seconds:02d}")
            
        except Exception as e:
            self._log(f"❌ Error actualizando display de estado: {e}")

    @pyqtSlot(str)
    def _handle_status_error(self, error_message: str):
        """Manejar errores del hilo de estado"""
        if hasattr(self, '_status_error_count'):
            self._status_error_count += 1
        else:
            self._status_error_count = 1
        
        # Solo loguear los primeros errores para evitar spam
        if self._status_error_count <= 5:
            self._log(f"⚠️ Error en hilo de estado: {error_message}")
        elif self._status_error_count == 6:
            self._log("⚠️ Suprimiendo errores adicionales del hilo de estado...")
        
        # Si hay demasiados errores, detener seguimiento
        if "Demasiados errores" in error_message:
            self._log("🛑 Deteniendo seguimiento por errores críticos del hilo de estado")
            self._stop_tracking()

    def update_detections(self, detections: list, frame_size: tuple = (1920, 1080)):
        """Actualizar detecciones para seguimiento - MÉTODO CORREGIDO DEFINITIVO"""
        try:
            # Verificar estado del seguimiento
            if not hasattr(self, 'tracking_active') or not self.tracking_active:
                return False

            if not hasattr(self, 'current_tracker') or not self.current_tracker:
                return False

            # Validar detecciones
            if not isinstance(detections, list):
                return False

            valid_detections = []
            for det in detections:
                if isinstance(det, dict) and 'bbox' in det and len(det.get('bbox', [])) == 4:
                    valid_detections.append(det)

            prev_frames = self.frames_without_detection
            if not valid_detections:
                self.frames_without_detection += 1
                if self.frames_without_detection >= 10:
                    self._zoom_out_search()
                if self.frames_without_detection >= 20:
                    self._recenter_on_last_known()
                return False
            else:
                if hasattr(self.current_tracker, 'get_position'):
                    pos = self.current_tracker.get_position()
                    if pos:
                        self.last_known_ptz = pos
                # Guardar historial de posición
                try:
                    best_det = max(valid_detections, key=lambda d: d.get('confidence', 0))
                    bx1, by1, bx2, by2 = best_det['bbox']
                    cx = (bx1 + bx2) / 2
                    cy = (by1 + by2) / 2
                    self.position_history.append({'center': (cx, cy), 'ptz': self.last_known_ptz})
                except Exception:
                    pass
                self.frames_without_detection = 0
                if prev_frames >= 10:
                    self._stop_current_movement()
                    if self.last_known_ptz and hasattr(self.current_tracker, 'absolute_move'):
                        try:
                            self.current_tracker.absolute_move(
                                self.last_known_ptz.get('pan', 0.0),
                                self.last_known_ptz.get('tilt', 0.0),
                                self.last_known_ptz.get('zoom'))
                        except Exception as e:
                            self._log(f"⚠️ Error retornando a última posición PTZ: {e}")

            # Incrementar contador de detecciones
            if not hasattr(self, 'detection_count'):
                self.detection_count = 0
            self.detection_count += len(valid_detections)

            # DIAGNÓSTICO: Verificar tipo de tracker UNA SOLA VEZ
            if not hasattr(self, '_tracker_type_identified'):
                tracker_class = self.current_tracker.__class__.__name__
                available_methods = [method for method in dir(self.current_tracker) 
                                   if not method.startswith('_') and callable(getattr(self.current_tracker, method))]
                
                self._log(f"🔍 Tracker identificado: {tracker_class}")
                self._log(f"🔍 Métodos disponibles: {', '.join(available_methods[:10])}...")  # Solo primeros 10
                self._tracker_type_identified = True
                self._tracker_class = tracker_class

            # LÓGICA SEGÚN EL TIPO DE TRACKER
            success = False

            # CASO 1: Tracker Multi-Objeto (MultiObjectPTZTracker)
            if hasattr(self.current_tracker, 'update_tracking'):
                try:
                    success = self.current_tracker.update_tracking(valid_detections, frame_size)
                    if not hasattr(self, '_method_logged'):
                        self._log("✅ Usando método: update_tracking")
                        self._method_logged = True
                except Exception as e:
                    self._log(f"❌ Error en update_tracking: {e}")

            # CASO 2: Sistema de Integración PTZ
            elif hasattr(self.current_tracker, 'track_objects'):
                try:
                    success = self.current_tracker.track_objects(valid_detections, frame_size)
                    if not hasattr(self, '_method_logged'):
                        self._log("✅ Usando método: track_objects")
                        self._method_logged = True
                except Exception as e:
                    self._log(f"❌ Error en track_objects: {e}")

            # CASO 3: Tracker Básico PTZCameraONVIF - IMPLEMENTAR SEGUIMIENTO MANUAL
            elif self._tracker_class == 'PTZCameraONVIF':
                success = self._handle_basic_ptz_tracking(valid_detections, frame_size)
                if not hasattr(self, '_method_logged'):
                    self._log("✅ Usando seguimiento básico PTZ manual")
                    self._method_logged = True

            # CASO 4: Otros trackers con process_detections
            elif hasattr(self.current_tracker, 'process_detections'):
                try:
                    success = self.current_tracker.process_detections(valid_detections, frame_size)
                    if not hasattr(self, '_method_logged'):
                        self._log("✅ Usando método: process_detections")
                        self._method_logged = True
                except Exception as e:
                    self._log(f"❌ Error en process_detections: {e}")

            # CASO 5: Tracker no compatible
            else:
                if not hasattr(self, '_incompatible_logged'):
                    self._log(f"⚠️ Tracker {self._tracker_class} no es compatible con seguimiento automático")
                    self._incompatible_logged = True
                return False

            # Loguear solo ocasionalmente para evitar spam
            if success and self.detection_count % 50 == 1:
                self._log(f"📊 Seguimiento activo - detecciones procesadas: {self.detection_count}")
            elif not success:
                if not hasattr(self, '_tracking_error_count'):
                    self._tracking_error_count = 0
                self._tracking_error_count += 1
                
                # Solo loguear cada 25 errores
                if self._tracking_error_count % 25 == 1:
                    self._log(f"⚠️ Error en seguimiento (#{self._tracking_error_count})")

            return success

        except Exception as e:
            self._log(f"❌ Error procesando detecciones: {e}")
            return False

    def _handle_basic_ptz_tracking(self, detections: list, frame_size: tuple) -> bool:
        """Manejar seguimiento para PTZCameraONVIF básico"""
        try:
            # Seleccionar la mejor detección (mayor confianza)
            best_detection = max(detections, key=lambda d: d.get('confidence', 0))
            
            # Extraer información de la detección
            bbox = best_detection['bbox']
            x1, y1, x2, y2 = bbox
            
            frame_w, frame_h = frame_size

            # Al detectar por primera vez, guardar preset temporal
            if self.detection_preset is None and hasattr(self.current_tracker, 'get_position'):
                pos = self.current_tracker.get_position()
                if pos:
                    self.detection_preset = pos
                    self.initial_zoom_level = pos.get('zoom', 0.0)

            # Solo controlaremos el zoom, sin mover pan/tilt
            pan_speed = 0.0
            tilt_speed = 0.0

            # ===== Control de ZOOM BÁSICO =====
            # Calcular área relativa del objeto en el frame
            obj_ratio = ((x2 - x1) * (y2 - y1)) / float(frame_w * frame_h)

            # Ratio objetivo desde la UI (0-1)
            target_ratio = self.target_size_slider.value() / 100.0

            # Velocidad base definida por el usuario
            base_zoom_speed = self.zoom_speed_slider.value() / 10.0

            # Determinar dirección de zoom
            zoom_speed = 0.0
            if obj_ratio < target_ratio:
                zoom_speed = base_zoom_speed
            elif obj_ratio > target_ratio:
                zoom_speed = -base_zoom_speed

            # No se ajusta pan/tilt, solo zoom

            # Aplicar zoom manteniendo la orientación del preset
            if self.detection_preset and hasattr(self.current_tracker, 'absolute_move'):
                current_zoom = self.detection_preset.get('zoom', 0.0)
                new_zoom = max(0.0, min(1.0, current_zoom + zoom_speed))
                self.current_tracker.absolute_move(
                    self.detection_preset.get('pan', 0.0),
                    self.detection_preset.get('tilt', 0.0),
                    new_zoom
                )
                self.detection_preset['zoom'] = new_zoom

                if hasattr(self.current_tracker, 'successful_moves'):
                    self.current_tracker.successful_moves += 1

                if self._stop_timer.isActive():
                    self._stop_timer.stop()
                self._stop_timer.start(100)
                return True
            elif hasattr(self.current_tracker, 'continuous_move'):
                self.current_tracker.continuous_move(pan_speed, tilt_speed, zoom_speed)

                if hasattr(self.current_tracker, 'successful_moves'):
                    self.current_tracker.successful_moves += 1

                if self._stop_timer.isActive():
                    self._stop_timer.stop()
                self._stop_timer.start(100)
                return True
            
            return False
            
        except Exception as e:
            self._log(f"❌ Error en seguimiento básico PTZ: {e}")
            if hasattr(self.current_tracker, 'failed_moves'):
                self.current_tracker.failed_moves += 1
            return False

    def _stop_current_movement(self):
        """Detener movimiento PTZ actual"""
        if self.current_tracker and hasattr(self.current_tracker, 'stop'):
            try:
                self.current_tracker.stop()
            except Exception as e:
                self._log(f"⚠️ Error deteniendo movimiento: {e}")

    def _zoom_out_search(self):
        """Realizar zoom out para buscar nuevas detecciones"""
        if self.current_tracker:
            try:
                if self.detection_preset and hasattr(self.current_tracker, 'absolute_move'):
                    current_zoom = self.detection_preset.get('zoom', 0.0)
                    target_zoom = max(self.initial_zoom_level or 0.0, current_zoom - self.search_zoom_speed)
                    self.current_tracker.absolute_move(
                        self.detection_preset.get('pan', 0.0),
                        self.detection_preset.get('tilt', 0.0),
                        target_zoom
                    )
                    self.detection_preset['zoom'] = target_zoom
                    if target_zoom <= (self.initial_zoom_level or 0.0):
                        self.detection_preset = None
                        self.initial_zoom_level = None
                elif hasattr(self.current_tracker, 'continuous_move'):
                    self.current_tracker.continuous_move(0.0, 0.0, -self.search_zoom_speed)
            except Exception as e:
                self._log(f"⚠️ Error ejecutando búsqueda por zoom: {e}")

    def _recenter_on_last_known(self):
        """Recentrar PTZ a la última posición conocida"""
        try:
            if not self.position_history or not self.current_tracker:
                return

            last_entry = self.position_history[-1]
            ptz = last_entry.get('ptz')

            if ptz and hasattr(self.current_tracker, 'absolute_move'):
                zoom_level = ptz.get('zoom')
                if self.initial_zoom_level is not None:
                    zoom_level = self.initial_zoom_level
                self.current_tracker.absolute_move(
                    ptz.get('pan', 0.0),
                    ptz.get('tilt', 0.0),
                    zoom_level
                )
        except Exception as e:
            self._log(f"⚠️ Error recentrando última posición: {e}")

    def _update_multi_config(self):
        """Actualizar configuración multi-objeto"""
        if not MULTI_OBJECT_AVAILABLE or not hasattr(self, 'alternating_cb'):
            return
        
        try:
            self.multi_config = self._get_current_multi_config()
            
            # Aplicar configuración al tracker actual si existe
            if self.current_tracker and hasattr(self.current_tracker, 'update_config'):
                self.current_tracker.update_config(self.multi_config)
                
        except Exception as e:
            self._log(f"⚠️ Error actualizando configuración multi-objeto: {e}")

    def _update_zoom_config(self):
        """Actualizar configuración de zoom"""
        try:
            if self.current_tracker and hasattr(self.current_tracker, 'set_auto_zoom'):
                self.current_tracker.set_auto_zoom(
                    enabled=self.auto_zoom_cb.isChecked(),
                    target_ratio=self.target_size_slider.value() / 100.0,
                    speed=self.zoom_speed_slider.value() / 10.0
                )
        except Exception as e:
            self._log(f"⚠️ Error actualizando configuración de zoom: {e}")

    def _update_ui_displays(self):
        """Actualizar displays de UI periódicamente"""
        try:
            # Actualizar tiempo de sesión si está activo
            if self.tracking_active and self.session_start_time > 0:
                elapsed = time.time() - self.session_start_time
                minutes = int(elapsed // 60)
                seconds = int(elapsed % 60)
                self.session_time_label.setText(f"{minutes:02d}:{seconds:02d}")
            
            # Actualizar contador de detecciones
            if hasattr(self, 'detection_count'):
                self.detections_label.setText(str(self.detection_count))
                
        except Exception as e:
            pass  # Error silencioso para evitar spam

    def _clear_log(self):
        """Limpiar log de actividad"""
        self.log_text.clear()
        self._log("🧹 Log limpiado")

    def _save_log(self):
        """Guardar log a archivo"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"ptz_log_{timestamp}.txt"
            
            filepath, _ = QFileDialog.getSaveFileName(
                self, "Guardar Log", filename, "Archivos de texto (*.txt)"
            )
            
            if filepath:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.toPlainText())
                self._log(f"📁 Log guardado en: {filepath}")
                
        except Exception as e:
            self._log(f"❌ Error guardando log: {e}")

    def _log(self, message: str):
        """Agregar mensaje al log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        
        # Agregar al widget de texto
        self.log_text.append(formatted_message)
        
        # Mantener solo las últimas 1000 líneas
        if self.log_text.document().lineCount() > 1000:
            cursor = self.log_text.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.movePosition(cursor.MoveOperation.Down, cursor.MoveMode.KeepAnchor, 100)
            cursor.removeSelectedText()
        
        # Auto-scroll al final
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
        # También imprimir en consola
        print(formatted_message)

    def _show_error_dialog(self):
        """Mostrar diálogo de error cuando no hay sistemas disponibles"""
        error_msg = """
Sistema PTZ no disponible.

Sistemas requeridos:
• core.multi_object_ptz_system
• core.ptz_tracking_integration_enhanced  
• core.ptz_control (básico)

Verifique que los archivos existen y las dependencias están instaladas.
        """
        QMessageBox.critical(self, "Error del Sistema", error_msg.strip())
        self.close()

    def set_detection_bridge(self, bridge):
        """Establecer el bridge de detecciones"""
        self.detection_bridge = bridge
        self._log("🌉 Bridge de detecciones configurado")

# === FUNCIONES DE UTILIDAD Y CREACIÓN ===

def create_multi_object_ptz_system(camera_list, parent=None):
    """Crear sistema PTZ multi-objeto completo con bridge de integración"""
    try:
        # Crear diálogo principal
        dialog = EnhancedMultiObjectPTZDialog(parent, camera_list)
        
        # Crear bridge de integración (clase completa para conectar con el sistema principal)
        class PTZDetectionBridge:
            """Puente de integración PTZ CORREGIDO"""

            def __init__(self, dialog):
                self.dialog = dialog
                self.active_cameras = {}
                self.detection_count = 0

            def send_detections(self, camera_id: str, detections: list, frame_size=(1920, 1080)):
                """Enviar detecciones al sistema PTZ - FIRMA CORREGIDA"""
                try:
                    # Validar parámetros
                    if not isinstance(camera_id, str):
                        print(f"❌ camera_id debe ser string, recibido: {type(camera_id)}")
                        return False

                    if not isinstance(detections, list):
                        print(f"❌ detections debe ser lista, recibido: {type(detections)}")
                        return False

                    if (not isinstance(frame_size, (tuple, list)) or len(frame_size) != 2):
                        print(f"❌ frame_size debe ser tupla de 2 elementos, recibido: {frame_size}")
                        return False

                    # Filtrar detecciones válidas
                    valid_detections = []
                    for det in detections:
                        if isinstance(det, dict) and 'bbox' in det:
                            bbox = det.get('bbox', [])
                            if len(bbox) == 4:
                                # Asegurar que bbox tiene valores numéricos válidos
                                try:
                                    x1, y1, x2, y2 = bbox
                                    if all(isinstance(coord, (int, float)) for coord in bbox):
                                        # Normalizar detección
                                        normalized_det = {
                                            'bbox': [float(x1), float(y1), float(x2), float(y2)],
                                            'confidence': float(det.get('confidence', det.get('conf', 0.5))),
                                            'class': det.get('class', det.get('cls', 'object')),
                                            'id': det.get('id', det.get('track_id', None))
                                        }
                                        valid_detections.append(normalized_det)
                                except (ValueError, TypeError):
                                    continue

                    if not valid_detections:
                        return False

                    # Registrar cámara si es nueva
                    if camera_id not in self.active_cameras:
                        self.active_cameras[camera_id] = {
                            'detections_sent': 0,
                            'last_detection': None
                        }

                    self.detection_count += len(valid_detections)
                    self.active_cameras[camera_id]['detections_sent'] += len(valid_detections)
                    self.active_cameras[camera_id]['last_detection'] = time.time()

                    # Enviar al diálogo PTZ
                    if self.dialog and hasattr(self.dialog, 'update_detections'):
                        return self.dialog.update_detections(valid_detections, frame_size)

                    return False

                except Exception as e:
                    print(f"❌ Error en PTZDetectionBridge.send_detections: {e}")
                    return False

            def register_camera(self, camera_id: str, camera_data: dict):
                """Registrar cámara en el bridge"""
                try:
                    self.active_cameras[camera_id] = {
                        'camera_data': camera_data,
                        'detections_sent': 0,
                        'registered_time': time.time()
                    }
                    return True
                except:
                    return False

            def get_status(self, camera_id=None):
                """Obtener estado del bridge"""
                if camera_id:
                    return self.active_cameras.get(camera_id, {})
                return {
                    'active_cameras': len(self.active_cameras),
                    'total_detections': self.detection_count,
                    'cameras': list(self.active_cameras.keys())
                }

            def cleanup(self):
                """Limpiar bridge"""
                self.active_cameras.clear()
                self.detection_count = 0

        # Crear bridge
        bridge = PTZDetectionBridge(dialog)
        
        # Conectar bridge al diálogo
        if hasattr(dialog, 'set_detection_bridge'):
            dialog.set_detection_bridge(bridge)
        
        # Crear wrapper del sistema
        class PTZSystemWrapper:
            """Wrapper para el sistema PTZ completo"""
            
            def __init__(self, dialog, bridge=None):
                self.dialog = dialog
                self.bridge = bridge
                
            def show(self):
                """Mostrar diálogo PTZ"""
                if self.dialog:
                    self.dialog.show()
                    
            def hide(self):
                """Ocultar diálogo PTZ"""
                if self.dialog:
                    self.dialog.hide()
                    
            def close(self):
                """Cerrar diálogo PTZ"""
                if self.dialog:
                    self.dialog.close()
                    
            def is_visible(self):
                """Verificar si el diálogo está visible"""
                return self.dialog and self.dialog.isVisible()
                
            def send_detections(self, camera_id, detections, frame_size=(1920, 1080)):
                """Enviar detecciones al sistema PTZ"""
                if self.bridge:
                    return self.bridge.send_detections(camera_id, detections, frame_size)
                return False
                
            def get_dialog(self):
                """Obtener referencia al diálogo"""
                return self.dialog
                
            def get_bridge(self):
                """Obtener referencia al bridge"""
                return self.bridge
        
        # Crear wrapper
        system = PTZSystemWrapper(dialog, bridge)
        
        return system
        
    except Exception as e:
        print(f"❌ Error creando sistema PTZ multi-objeto: {e}")
        return None

# === FUNCIONES AUXILIARES ===

def test_ptz_system_availability():
    """Probar disponibilidad de sistemas PTZ"""
    results = {
        'multi_object': MULTI_OBJECT_AVAILABLE,
        'integration': INTEGRATION_AVAILABLE,  
        'basic_ptz': BASIC_PTZ_AVAILABLE
    }
    
    print("🔍 Estado de sistemas PTZ:")
    for system, available in results.items():
        status = "✅ Disponible" if available else "❌ No disponible"
        print(f"  {system}: {status}")
    
    return results

def get_ptz_system_info():
    """Obtener información detallada de sistemas PTZ"""
    info = {
        'systems': {
            'multi_object': {
                'available': MULTI_OBJECT_AVAILABLE,
                'description': 'Sistema avanzado multi-objeto con alternancia y zoom inteligente'
            },
            'integration': {
                'available': INTEGRATION_AVAILABLE,
                'description': 'Sistema de integración PTZ mejorado con gestión de sesiones'
            },
            'basic': {
                'available': BASIC_PTZ_AVAILABLE,
                'description': 'Control PTZ básico ONVIF'
            }
        },
        'recommended_order': [
            'multi_object' if MULTI_OBJECT_AVAILABLE else None,
            'integration' if INTEGRATION_AVAILABLE else None, 
            'basic' if BASIC_PTZ_AVAILABLE else None
        ]
    }
    
    # Filtrar sistemas no disponibles
    info['recommended_order'] = [s for s in info['recommended_order'] if s is not None]
    
    return info

# === PUNTO DE ENTRADA PRINCIPAL ===

if __name__ == "__main__":
    """Modo de prueba del diálogo PTZ"""
    import sys
    from PyQt6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    
    # Datos de prueba
    test_cameras = [
        {
            'nombre': 'PTZ Camera 1',
            'ip': '192.168.1.100',
            'puerto': 80,
            'usuario': 'admin',
            'contrasena': 'admin123',
            'tipo': 'ptz'
        },
        {
            'nombre': 'PTZ Camera 2', 
            'ip': '192.168.1.101',
            'puerto': 80,
            'usuario': 'admin',
            'contrasena': 'admin123',
            'tipo': 'ptz'
        }
    ]
    
    # Crear y mostrar diálogo
    dialog = EnhancedMultiObjectPTZDialog(None, test_cameras)
    dialog.show()
    
    print("🎯 Diálogo PTZ Multi-Objeto iniciado en modo de prueba")
    print("📋 Funcionalidades disponibles:")
    
    availability = test_ptz_system_availability()
    if not any(availability.values()):
        print("⚠️ ADVERTENCIA: No hay sistemas PTZ disponibles")
        print("  El diálogo se ejecutará pero sin funcionalidad PTZ")
    
    sys.exit(app.exec())
