# gui/components/asistente_rapido.py
"""
Asistente Rápido PTZ - Configuración automática inteligente.
Responsabilidades:
- Configuración automática de PTZ por geometría de grilla
- Asistente paso a paso para ajuste de zoom
- Vista previa en tiempo real
- Configuración masiva y personalizada
- Integración completa con arquitectura modular
"""

import time
import math
from typing import Dict, Any, Optional, Tuple, List
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QSlider, QGroupBox, QFormLayout,
                             QSpinBox, QProgressDialog, QMessageBox, QComboBox,
                             QCheckBox, QApplication, QTabWidget, QWidget,
                             QTextEdit, QGridLayout, QFrame, QScrollArea)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QObject
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QPen


class AsistenteRapidoPTZ(QObject):
    """
    Asistente Rápido PTZ integrado con arquitectura modular
    """
    
    # Señales
    configuration_completed = pyqtSignal(dict)  # Configuración completada
    preview_updated = pyqtSignal(int, int)      # Vista previa actualizada (row, col)
    log_message = pyqtSignal(str)               # Mensaje de log
    
    def __init__(self, grilla_widget):
        super().__init__()
        self.grilla_widget = grilla_widget
        self.cell_manager = grilla_widget.cell_manager
        self.ptz_manager = grilla_widget.ptz_manager
        self.config_manager = grilla_widget.config_manager
        self.grid_renderer = grilla_widget.grid_renderer
        
        # Estado del asistente
        self.current_cell: Optional[Tuple[int, int]] = None
        self.current_ptz_ip: Optional[str] = None
        self.cell_configurations: Dict[Tuple[int, int], Dict[str, Any]] = {}
        self.preview_active = False
        
        # Configuración de cobertura
        self.horizontal_coverage = 90  # Grados
        self.vertical_coverage = 60    # Grados
        self.default_zoom = 40         # Porcentaje
        
        # Timer para vista previa
        self.preview_timer = QTimer()
        self.preview_timer.timeout.connect(self._update_preview)
        
        # Dialog principal
        self.dialog: Optional[QDialog] = None
    
    def show_asistente_rapido(self):
        """Muestra el asistente rápido PTZ"""
        if not self.ptz_manager.get_ptz_cameras():
            QMessageBox.warning(
                self.grilla_widget, 
                "Sin Cámaras PTZ", 
                "No hay cámaras PTZ configuradas.\n\n"
                "Configura al menos una cámara PTZ antes de usar el asistente."
            )
            return
        
        self.dialog = QDialog(self.grilla_widget)
        self.dialog.setWindowTitle("🚀 Asistente Rápido PTZ")
        self.dialog.setMinimumSize(1000, 700)
        self.dialog.setModal(True)
        
        self._setup_ui()
        self._load_initial_state()
        
        # Mostrar diálogo
        result = self.dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            self._finalize_configuration()
    
    def _setup_ui(self):
        """Configura la interfaz del asistente"""
        layout = QHBoxLayout(self.dialog)
        
        # Panel izquierdo: Controles
        self._setup_control_panel(layout)
        
        # Panel central: Vista previa de grilla
        self._setup_grid_preview_panel(layout)
        
        # Panel derecho: Configuración y estadísticas
        self._setup_stats_panel(layout)
        
        # Panel inferior: Acciones
        self._setup_action_panel()
    
    def _setup_control_panel(self, main_layout):
        """Configura el panel de controles izquierdo"""
        control_scroll = QScrollArea()
        control_widget = QWidget()
        control_scroll.setWidget(control_widget)
        control_scroll.setWidgetResizable(True)
        control_scroll.setMaximumWidth(350)
        
        layout = QVBoxLayout(control_widget)
        
        # === CONFIGURACIÓN PTZ ===
        ptz_group = self._create_ptz_config_group()
        layout.addWidget(ptz_group)
        
        # === CONFIGURACIÓN DE GRILLA ===
        grid_group = self._create_grid_config_group()
        layout.addWidget(grid_group)
        
        # === CONFIGURACIÓN DE ZOOM ===
        zoom_group = self._create_zoom_config_group()
        layout.addWidget(zoom_group)
        
        # === NAVEGACIÓN POR CELDAS ===
        nav_group = self._create_navigation_group()
        layout.addWidget(nav_group)
        
        # === ACCIONES RÁPIDAS ===
        actions_group = self._create_quick_actions_group()
        layout.addWidget(actions_group)
        
        main_layout.addWidget(control_scroll)
    
    def _create_ptz_config_group(self):
        """Crea grupo de configuración PTZ"""
        group = QGroupBox("🎯 Configuración PTZ")
        layout = QFormLayout()
        
        # Selector de cámara PTZ
        self.ptz_combo = QComboBox()
        for ptz_ip in self.ptz_manager.get_ptz_cameras():
            ptz_info = self.ptz_manager.get_camera_info(ptz_ip)
            display_text = f"🎯 {ptz_ip}"
            if ptz_info:
                display_text += f" ({ptz_info.get('usuario', 'admin')})"
            self.ptz_combo.addItem(display_text, ptz_ip)
        
        # Estado de conexión
        self.connection_status = QLabel("🔴 Desconectado")
        
        # Botón de prueba
        self.test_ptz_btn = QPushButton("🧪 Probar Conexión")
        self.test_ptz_btn.clicked.connect(self._test_ptz_connection)
        
        layout.addRow("Cámara PTZ:", self.ptz_combo)
        layout.addRow("Estado:", self.connection_status)
        layout.addRow("", self.test_ptz_btn)
        
        group.setLayout(layout)
        
        # Conectar señales
        self.ptz_combo.currentTextChanged.connect(self._on_ptz_changed)
        
        return group
    
    def _create_grid_config_group(self):
        """Crea grupo de configuración de grilla"""
        group = QGroupBox("📐 Configuración de Grilla")
        layout = QFormLayout()
        
        # Cobertura horizontal
        self.horizontal_spin = QSpinBox()
        self.horizontal_spin.setRange(30, 180)
        self.horizontal_spin.setValue(self.horizontal_coverage)
        self.horizontal_spin.setSuffix("°")
        self.horizontal_spin.valueChanged.connect(self._on_coverage_changed)
        
        # Cobertura vertical
        self.vertical_spin = QSpinBox()
        self.vertical_spin.setRange(20, 120)
        self.vertical_spin.setValue(self.vertical_coverage)
        self.vertical_spin.setSuffix("°")
        self.vertical_spin.valueChanged.connect(self._on_coverage_changed)
        
        # Información de grilla
        grid_info = f"{self.cell_manager.filas}×{self.cell_manager.columnas} celdas"
        self.grid_info_label = QLabel(grid_info)
        
        layout.addRow("Cobertura horizontal:", self.horizontal_spin)
        layout.addRow("Cobertura vertical:", self.vertical_spin)
        layout.addRow("Tamaño de grilla:", self.grid_info_label)
        
        group.setLayout(layout)
        return group
    
    def _create_zoom_config_group(self):
        """Crea grupo de configuración de zoom"""
        group = QGroupBox("🔍 Configuración de Zoom")
        layout = QVBoxLayout()
        
        # Zoom por defecto
        form_layout = QFormLayout()
        
        self.default_zoom_spin = QSpinBox()
        self.default_zoom_spin.setRange(10, 100)
        self.default_zoom_spin.setValue(self.default_zoom)
        self.default_zoom_spin.setSuffix("%")
        
        form_layout.addRow("Zoom por defecto:", self.default_zoom_spin)
        layout.addLayout(form_layout)
        
        # Zoom por zona
        zone_layout = QHBoxLayout()
        
        self.zone_close_btn = QPushButton("Cerca (20%)")
        self.zone_medium_btn = QPushButton("Medio (40%)")
        self.zone_far_btn = QPushButton("Lejos (80%)")
        
        self.zone_close_btn.clicked.connect(lambda: self._set_default_zoom(20))
        self.zone_medium_btn.clicked.connect(lambda: self._set_default_zoom(40))
        self.zone_far_btn.clicked.connect(lambda: self._set_default_zoom(80))
        
        zone_layout.addWidget(self.zone_close_btn)
        zone_layout.addWidget(self.zone_medium_btn)
        zone_layout.addWidget(self.zone_far_btn)
        
        layout.addLayout(zone_layout)
        
        # Zoom personalizado para celda actual
        if self.current_cell:
            custom_layout = QFormLayout()
            
            self.custom_zoom_slider = QSlider(Qt.Orientation.Horizontal)
            self.custom_zoom_slider.setRange(10, 100)
            self.custom_zoom_slider.setValue(self.default_zoom)
            
            self.custom_zoom_label = QLabel(f"{self.default_zoom}%")
            self.custom_zoom_slider.valueChanged.connect(self._on_custom_zoom_changed)
            
            custom_layout.addRow("Zoom celda actual:", self.custom_zoom_slider)
            custom_layout.addRow("", self.custom_zoom_label)
            
            layout.addLayout(custom_layout)
        
        group.setLayout(layout)
        return group
    
    def _create_navigation_group(self):
        """Crea grupo de navegación por celdas"""
        group = QGroupBox("🧭 Navegación por Celdas")
        layout = QVBoxLayout()
        
        # Información de celda actual
        self.cell_info_label = QLabel("Haz clic en una celda para comenzar")
        self.cell_info_label.setStyleSheet("font-weight: bold; color: #2E5BBA;")
        layout.addWidget(self.cell_info_label)
        
        # Botones de navegación
        nav_layout = QHBoxLayout()
        
        self.prev_btn = QPushButton("⬅️ Anterior")
        self.next_btn = QPushButton("Siguiente ➡️")
        
        self.prev_btn.clicked.connect(self._navigate_previous)
        self.next_btn.clicked.connect(self._navigate_next)
        
        nav_layout.addWidget(self.prev_btn)
        nav_layout.addWidget(self.next_btn)
        layout.addLayout(nav_layout)
        
        # Posicionamiento automático
        self.auto_position_btn = QPushButton("📍 Posicionar Automáticamente")
        self.auto_position_btn.setStyleSheet(
            "background-color: #4CAF50; color: white; font-weight: bold; padding: 8px;"
        )
        self.auto_position_btn.clicked.connect(self._auto_position_current_cell)
        layout.addWidget(self.auto_position_btn)
        
        # Guardar celda actual
        self.save_cell_btn = QPushButton("💾 Guardar Configuración de Celda")
        self.save_cell_btn.setStyleSheet(
            "background-color: #2196F3; color: white; font-weight: bold; padding: 6px;"
        )
        self.save_cell_btn.clicked.connect(self._save_current_cell)
        layout.addWidget(self.save_cell_btn)
        
        group.setLayout(layout)
        return group
    
    def _create_quick_actions_group(self):
        """Crea grupo de acciones rápidas"""
        group = QGroupBox("⚡ Acciones Rápidas")
        layout = QVBoxLayout()
        
        # Configuración automática completa
        self.auto_config_btn = QPushButton("🤖 Configuración Automática Completa")
        self.auto_config_btn.setStyleSheet(
            "background-color: #FF9800; color: white; font-weight: bold; padding: 10px;"
        )
        self.auto_config_btn.clicked.connect(self._auto_configure_all)
        layout.addWidget(self.auto_config_btn)
        
        # Aplicar zoom actual a todas las celdas
        self.apply_zoom_all_btn = QPushButton("🔍 Aplicar Zoom a Todas las Celdas")
        self.apply_zoom_all_btn.clicked.connect(self._apply_zoom_to_all)
        layout.addWidget(self.apply_zoom_all_btn)
        
        # Limpiar configuración
        self.clear_config_btn = QPushButton("🗑️ Limpiar Configuración PTZ")
        self.clear_config_btn.clicked.connect(self._clear_ptz_configuration)
        layout.addWidget(self.clear_config_btn)
        
        group.setLayout(layout)
        return group
    
    def _setup_grid_preview_panel(self, main_layout):
        """Configura el panel de vista previa de grilla"""
        preview_group = QGroupBox("📹 Vista Previa de Grilla")
        preview_layout = QVBoxLayout()
        
        # Widget de vista previa personalizado
        self.grid_preview = GridPreviewWidget(
            self.cell_manager, 
            self.cell_configurations,
            parent=self.dialog
        )
        self.grid_preview.setMinimumSize(400, 300)
        self.grid_preview.cell_clicked.connect(self._on_grid_cell_clicked)
        
        preview_layout.addWidget(self.grid_preview)
        
        # Controles de vista previa
        preview_controls = QHBoxLayout()
        
        self.preview_enable_check = QCheckBox("🔴 Vista Previa en Tiempo Real")
        self.preview_enable_check.stateChanged.connect(self._toggle_preview)
        
        self.show_coverage_check = QCheckBox("📐 Mostrar Cobertura PTZ")
        self.show_coverage_check.setChecked(True)
        self.show_coverage_check.stateChanged.connect(self.grid_preview.update)
        
        preview_controls.addWidget(self.preview_enable_check)
        preview_controls.addWidget(self.show_coverage_check)
        preview_controls.addStretch()
        
        preview_layout.addLayout(preview_controls)
        
        preview_group.setLayout(preview_layout)
        main_layout.addWidget(preview_group)
    
    def _setup_stats_panel(self, main_layout):
        """Configura el panel de estadísticas"""
        stats_scroll = QScrollArea()
        stats_widget = QWidget()
        stats_scroll.setWidget(stats_widget)
        stats_scroll.setWidgetResizable(True)
        stats_scroll.setMaximumWidth(300)
        
        layout = QVBoxLayout(stats_widget)
        
        # === ESTADÍSTICAS ===
        stats_group = QGroupBox("📊 Estadísticas")
        stats_layout = QFormLayout()
        
        self.total_cells_label = QLabel("0")
        self.configured_cells_label = QLabel("0")
        self.coverage_label = QLabel("0%")
        self.avg_zoom_label = QLabel("0%")
        
        stats_layout.addRow("Total de celdas:", self.total_cells_label)
        stats_layout.addRow("Celdas configuradas:", self.configured_cells_label)
        stats_layout.addRow("Cobertura:", self.coverage_label)
        stats_layout.addRow("Zoom promedio:", self.avg_zoom_label)
        
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)
        
        # === LOG DE ACTIVIDAD ===
        log_group = QGroupBox("📝 Log de Actividad")
        log_layout = QVBoxLayout()
        
        self.activity_log = QTextEdit()
        self.activity_log.setMaximumHeight(200)
        self.activity_log.setStyleSheet(
            "background-color: #1e1e1e; color: #ffffff; font-family: monospace;"
        )
        
        log_layout.addWidget(self.activity_log)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        # === CONFIGURACIÓN ACTUAL ===
        config_group = QGroupBox("⚙️ Configuración Actual")
        config_layout = QVBoxLayout()
        
        self.config_summary = QTextEdit()
        self.config_summary.setMaximumHeight(150)
        self.config_summary.setReadOnly(True)
        
        config_layout.addWidget(self.config_summary)
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)
        
        main_layout.addWidget(stats_scroll)
    
    def _setup_action_panel(self):
        """Configura el panel de acciones inferior"""
        action_frame = QFrame()
        action_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        action_layout = QHBoxLayout(action_frame)
        
        # Botón de ayuda
        help_btn = QPushButton("❓ Ayuda")
        help_btn.clicked.connect(self._show_help)
        
        # Botón de exportar configuración
        export_btn = QPushButton("📤 Exportar Configuración")
        export_btn.clicked.connect(self._export_configuration)
        
        # Espaciador
        action_layout.addWidget(help_btn)
        action_layout.addWidget(export_btn)
        action_layout.addStretch()
        
        # Botones principales
        self.apply_btn = QPushButton("✅ Aplicar y Guardar")
        self.apply_btn.setStyleSheet(
            "background-color: #4CAF50; color: white; font-weight: bold; padding: 10px 20px;"
        )
        self.apply_btn.clicked.connect(self._apply_configuration)
        
        cancel_btn = QPushButton("❌ Cancelar")
        cancel_btn.clicked.connect(self.dialog.reject)
        
        action_layout.addWidget(self.apply_btn)
        action_layout.addWidget(cancel_btn)
        
        # Agregar al layout principal del diálogo
        self.dialog.layout().addWidget(action_frame)
    
    # === MANEJADORES DE EVENTOS ===
    
    def _on_ptz_changed(self):
        """Maneja cambio de cámara PTZ seleccionada"""
        if self.ptz_combo.currentData():
            self.current_ptz_ip = self.ptz_combo.currentData()
            self._test_ptz_connection()
            self._log_activity(f"Cámara PTZ seleccionada: {self.current_ptz_ip}")
    
    def _on_coverage_changed(self):
        """Maneja cambio en configuración de cobertura"""
        self.horizontal_coverage = self.horizontal_spin.value()
        self.vertical_coverage = self.vertical_spin.value()
        
        # Actualizar vista previa
        self.grid_preview.update()
        self._log_activity(f"Cobertura actualizada: {self.horizontal_coverage}°×{self.vertical_coverage}°")
    
    def _on_custom_zoom_changed(self, value):
        """Maneja cambio en zoom personalizado"""
        self.custom_zoom_label.setText(f"{value}%")
        
        # Aplicar a celda actual si existe
        if self.current_cell:
            if self.current_cell not in self.cell_configurations:
                self.cell_configurations[self.current_cell] = {}
            self.cell_configurations[self.current_cell]["zoom"] = value / 100.0
            self._update_statistics()
    
    def _on_grid_cell_clicked(self, row, col):
        """Maneja clic en celda de grilla"""
        self.current_cell = (row, col)
        self._update_cell_info()
        self._update_zoom_controls()
        self._log_activity(f"Celda seleccionada: ({row},{col})")
    
    # === OPERACIONES PTZ ===
    
    def _test_ptz_connection(self):
        """Prueba la conexión PTZ"""
        if not self.current_ptz_ip:
            return
        
        self.connection_status.setText("🟡 Probando...")
        QApplication.processEvents()
        
        success = self.ptz_manager.test_ptz_connection(self.current_ptz_ip)
        
        if success:
            self.connection_status.setText("🟢 Conectado")
            self._log_activity(f"✅ Conexión PTZ exitosa: {self.current_ptz_ip}")
        else:
            self.connection_status.setText("🔴 Error de conexión")
            self._log_activity(f"❌ Error de conexión PTZ: {self.current_ptz_ip}")
    
    def _auto_position_current_cell(self):
        """Posiciona automáticamente la PTZ en la celda actual"""
        if not self.current_cell or not self.current_ptz_ip:
            return
        
        row, col = self.current_cell
        position = self._calculate_cell_position(row, col)
        
        # Mover PTZ
        success = self.ptz_manager.move_absolute(
            self.current_ptz_ip,
            position["pan"],
            position["tilt"],
            position["zoom"],
            speed=0.5
        )
        
        if success:
            self._log_activity(f"📍 PTZ posicionada en celda ({row},{col})")
            
            # Mostrar vista previa simulada
            self._simulate_preview()
        else:
            self._log_activity(f"❌ Error posicionando PTZ en celda ({row},{col})")
    
    def _calculate_cell_position(self, row: int, col: int) -> Dict[str, float]:
        """Calcula la posición PTZ para una celda específica"""
        # Centro de la celda en coordenadas normalizadas
        cell_center_x = (col + 0.5) / self.cell_manager.columnas
        cell_center_y = (row + 0.5) / self.cell_manager.filas
        
        # Aplicar factor de cobertura
        coverage_factor_h = self.horizontal_coverage / 180.0
        coverage_factor_v = self.vertical_coverage / 120.0
        
        # Convertir a coordenadas PTZ (-1.0 a 1.0)
        ptz_pan = (cell_center_x - 0.5) * 2.0 * coverage_factor_h
        ptz_tilt = (0.5 - cell_center_y) * 2.0 * coverage_factor_v
        
        # Limitar rangos
        ptz_pan = max(-1.0, min(1.0, ptz_pan))
        ptz_tilt = max(-1.0, min(1.0, ptz_tilt))
        
        # Zoom personalizado o por defecto
        zoom = self.default_zoom / 100.0
        if self.current_cell in self.cell_configurations:
            zoom = self.cell_configurations[self.current_cell].get("zoom", zoom)
        
        return {
            "pan": ptz_pan,
            "tilt": ptz_tilt,
            "zoom": zoom
        }
    
    # === CONFIGURACIÓN AUTOMÁTICA ===
    
    def _auto_configure_all(self):
        """Configuración automática para todas las celdas"""
        if not self.current_ptz_ip:
            QMessageBox.warning(
                self.dialog,
                "Sin PTZ",
                "Selecciona una cámara PTZ primero."
            )
            return
        
        reply = QMessageBox.question(
            self.dialog,
            "Configuración Automática",
            f"¿Configurar automáticamente todas las {self.cell_manager.filas}×{self.cell_manager.columnas} celdas?\n\n"
            f"Esto calculará posiciones PTZ automáticamente usando:\n"
            f"• Cobertura: {self.horizontal_coverage}°×{self.vertical_coverage}°\n"
            f"• Zoom por defecto: {self.default_zoom}%",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # Mostrar progreso
        progress = QProgressDialog(
            "Configurando celdas automáticamente...", 
            "Cancelar", 
            0, 
            self.cell_manager.filas * self.cell_manager.columnas, 
            self.dialog
        )
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        
        configured_count = 0
        
        for row in range(self.cell_manager.filas):
            for col in range(self.cell_manager.columnas):
                if progress.wasCanceled():
                    break
                
                # Calcular posición
                position = self._calculate_cell_position(row, col)
                
                # Guardar configuración
                self.cell_configurations[(row, col)] = {
                    "ip": self.current_ptz_ip,
                    "type": "absolute_with_zoom",
                    "pan": position["pan"],
                    "tilt": position["tilt"],
                    "zoom": position["zoom"],
                    "auto_generated": True
                }
                
                configured_count += 1
                progress.setValue(configured_count)
                QApplication.processEvents()
        
        progress.close()
        
        if not progress.wasCanceled():
            self._update_statistics()
            self.grid_preview.update()
            self._log_activity(f"✅ {configured_count} celdas configuradas automáticamente")
            
            QMessageBox.information(
                self.dialog,
                "Configuración Completa",
                f"✅ {configured_count} celdas configuradas exitosamente.\n\n"
                f"Puedes ajustar zoom individualmente o aplicar la configuración."
            )
    
    def _apply_zoom_to_all(self):
        """Aplica el zoom actual a todas las celdas configuradas"""
        zoom_value = self.default_zoom / 100.0
        applied_count = 0
        
        for cell_coords in self.cell_configurations:
            if "zoom" in self.cell_configurations[cell_coords]:
                self.cell_configurations[cell_coords]["zoom"] = zoom_value
                applied_count += 1
        
        self._update_statistics()
        self._log_activity(f"🔍 Zoom {self.default_zoom}% aplicado a {applied_count} celdas")
    
    def _clear_ptz_configuration(self):
        """Limpia toda la configuración PTZ"""
        reply = QMessageBox.question(
            self.dialog,
            "Limpiar Configuración",
            "¿Estás seguro de que quieres eliminar toda la configuración PTZ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.cell_configurations.clear()
            self._update_statistics()
            self.grid_preview.update()
            self._log_activity("🗑️ Configuración PTZ limpiada")
    
    # === NAVEGACIÓN ===
    
    def _navigate_previous(self):
        """Navega a la celda anterior"""
        if not self.current_cell:
            self.current_cell = (0, 0)
        else:
            row, col = self.current_cell
            if col > 0:
                col -= 1
            elif row > 0:
                row -= 1
                col = self.cell_manager.columnas - 1
            
            self.current_cell = (row, col)
        
        self._update_cell_info()
        self.grid_preview.set_selected_cell(self.current_cell)
    
    def _navigate_next(self):
        """Navega a la siguiente celda"""
        if not self.current_cell:
            self.current_cell = (0, 0)
        else:
            row, col = self.current_cell
            if col < self.cell_manager.columnas - 1:
                col += 1
            elif row < self.cell_manager.filas - 1:
                row += 1
                col = 0
            
            self.current_cell = (row, col)
        
        self._update_cell_info()
        self.grid_preview.set_selected_cell(self.current_cell)
    
    # === PERSISTENCIA ===
    
    def _save_current_cell(self):
        """Guarda la configuración de la celda actual"""
        if not self.current_cell or not self.current_ptz_ip:
            return
        
        row, col = self.current_cell
        position = self._calculate_cell_position(row, col)
        
        self.cell_configurations[self.current_cell] = {
            "ip": self.current_ptz_ip,
            "type": "absolute_with_zoom",
            "pan": position["pan"],
            "tilt": position["tilt"],
            "zoom": position["zoom"],
            "manual_configured": True,
            "timestamp": time.time()
        }
        
        self._update_statistics()
        self.grid_preview.update()
        self._log_activity(f"💾 Celda ({row},{col}) guardada con zoom {position['zoom']*100:.0f}%")
        
        # Auto-navegar a siguiente celda
        self._navigate_next()
    
    def _apply_configuration(self):
        """Aplica toda la configuración al sistema"""
        if not self.cell_configurations:
            QMessageBox.warning(
                self.dialog,
                "Sin Configuración",
                "No hay configuración para aplicar.\n\n"
                "Usa 'Configuración Automática' o configura celdas individualmente."
            )
            return
        
        # Confirmar aplicación
        reply = QMessageBox.question(
            self.dialog,
            "Aplicar Configuración",
            f"¿Aplicar configuración PTZ a {len(self.cell_configurations)} celdas?\n\n"
            f"Esto sobrescribirá cualquier configuración PTZ existente en esas celdas.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # Aplicar al CellManager
        applied_count = 0
        for cell_coords, config in self.cell_configurations.items():
            success = self.cell_manager.set_cell_ptz_mapping(
                cell_coords[0], 
                cell_coords[1], 
                config
            )
            if success:
                applied_count += 1
        
        # Guardar configuración
        self.config_manager.save_grid_state(self.cell_manager)
        
        # Emitir señal de completado
        self.configuration_completed.emit({"applied_cells": applied_count})
        
        QMessageBox.information(
            self.dialog,
            "✅ Configuración Aplicada",
            f"Configuración PTZ aplicada exitosamente a {applied_count} celdas.\n\n"
            f"El sistema automático está ahora activo."
        )
        
        self.dialog.accept()
    
    def _finalize_configuration(self):
        """Finaliza la configuración al cerrar el asistente"""
        self._log_activity("✅ Asistente PTZ finalizado")
    
    # === UTILIDADES DE INTERFAZ ===
    
    def _load_initial_state(self):
        """Carga el estado inicial del asistente"""
        # Seleccionar primera cámara PTZ
        if self.ptz_combo.count() > 0:
            self.current_ptz_ip = self.ptz_combo.itemData(0)
            self._test_ptz_connection()
        
        # Cargar configuración existente si existe
        self._load_existing_configuration()
        
        # Actualizar estadísticas
        self._update_statistics()
        
        self._log_activity("🚀 Asistente PTZ iniciado")
    
    def _load_existing_configuration(self):
        """Carga configuración PTZ existente"""
        existing_count = 0
        
        for (row, col), ptz_mapping in self.cell_manager.cell_ptz_map.items():
            if ptz_mapping.get("type") in ["absolute_with_zoom", "absolute"]:
                self.cell_configurations[(row, col)] = ptz_mapping.copy()
                existing_count += 1
        
        if existing_count > 0:
            self._log_activity(f"📁 {existing_count} configuraciones existentes cargadas")
            self.grid_preview.update()
    
    def _update_cell_info(self):
        """Actualiza información de la celda actual"""
        if not self.current_cell:
            self.cell_info_label.setText("Ninguna celda seleccionada")
            return
        
        row, col = self.current_cell
        
        # Información básica
        info_text = f"Celda actual: ({row},{col})"
        
        # Estado de configuración
        if self.current_cell in self.cell_configurations:
            config = self.cell_configurations[self.current_cell]
            zoom = config.get("zoom", 0) * 100
            info_text += f"\n✅ Configurada (Zoom: {zoom:.0f}%)"
        else:
            info_text += f"\n⚪ Sin configurar"
        
        # Estado en CellManager
        if self.cell_manager.is_cell_discarded(row, col):
            info_text += f"\n❌ Celda descartada"
        elif self.cell_manager.has_cell_ptz_mapping(row, col):
            info_text += f"\n🎯 PTZ ya asignado"
        
        self.cell_info_label.setText(info_text)
    
    def _update_zoom_controls(self):
        """Actualiza controles de zoom para celda actual"""
        if not self.current_cell or not hasattr(self, 'custom_zoom_slider'):
            return
        
        # Cargar zoom de configuración si existe
        zoom_value = self.default_zoom
        if self.current_cell in self.cell_configurations:
            config_zoom = self.cell_configurations[self.current_cell].get("zoom", 0)
            zoom_value = int(config_zoom * 100)
        
        self.custom_zoom_slider.setValue(zoom_value)
        self.custom_zoom_label.setText(f"{zoom_value}%")
    
    def _update_statistics(self):
        """Actualiza las estadísticas mostradas"""
        total_cells = self.cell_manager.filas * self.cell_manager.columnas
        configured_cells = len(self.cell_configurations)
        coverage_percent = (configured_cells / total_cells) * 100 if total_cells > 0 else 0
        
        # Calcular zoom promedio
        avg_zoom = 0
        if self.cell_configurations:
            zoom_sum = sum(config.get("zoom", 0) for config in self.cell_configurations.values())
            avg_zoom = (zoom_sum / len(self.cell_configurations)) * 100
        
        # Actualizar labels
        self.total_cells_label.setText(str(total_cells))
        self.configured_cells_label.setText(str(configured_cells))
        self.coverage_label.setText(f"{coverage_percent:.1f}%")
        self.avg_zoom_label.setText(f"{avg_zoom:.0f}%")
        
        # Actualizar resumen de configuración
        self._update_configuration_summary()
    
    def _update_configuration_summary(self):
        """Actualiza el resumen de configuración"""
        if not self.cell_configurations:
            self.config_summary.setText("Sin configuración PTZ")
            return
        
        summary_lines = [
            f"🎯 PTZ: {self.current_ptz_ip or 'No seleccionada'}",
            f"📐 Cobertura: {self.horizontal_coverage}°×{self.vertical_coverage}°",
            f"🔍 Zoom por defecto: {self.default_zoom}%",
            f"📊 Celdas configuradas: {len(self.cell_configurations)}",
            "",
            "📋 Resumen por tipo:",
        ]
        
        # Contar tipos de configuración
        auto_count = sum(1 for config in self.cell_configurations.values() 
                        if config.get("auto_generated", False))
        manual_count = sum(1 for config in self.cell_configurations.values() 
                          if config.get("manual_configured", False))
        
        if auto_count > 0:
            summary_lines.append(f"  🤖 Automática: {auto_count}")
        if manual_count > 0:
            summary_lines.append(f"  ✋ Manual: {manual_count}")
        
        self.config_summary.setText("\n".join(summary_lines))
    
    def _set_default_zoom(self, zoom_percent: int):
        """Establece zoom por defecto"""
        self.default_zoom = zoom_percent
        self.default_zoom_spin.setValue(zoom_percent)
        self._log_activity(f"🔍 Zoom por defecto: {zoom_percent}%")
    
    def _toggle_preview(self, enabled: bool):
        """Habilita/deshabilita vista previa en tiempo real"""
        self.preview_active = enabled
        
        if enabled:
            self.preview_timer.start(1000)  # Actualizar cada segundo
            self._log_activity("🔴 Vista previa activada")
        else:
            self.preview_timer.stop()
            self._log_activity("⚫ Vista previa desactivada")
    
    def _update_preview(self):
        """Actualiza la vista previa en tiempo real"""
        if self.current_cell and self.current_ptz_ip:
            # Simular actualización de vista previa
            self.preview_updated.emit(*self.current_cell)
    
    def _simulate_preview(self):
        """Simula vista previa después de posicionamiento"""
        if self.current_cell:
            row, col = self.current_cell
            self.grid_preview.highlight_cell(row, col, duration=2000)
    
    def _log_activity(self, message: str):
        """Registra actividad en el log"""
        timestamp = time.strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        
        self.activity_log.append(log_entry)
        self.activity_log.verticalScrollBar().setValue(
            self.activity_log.verticalScrollBar().maximum()
        )
        
        # Emitir señal para log principal
        self.log_message.emit(message)
    
    # === FUNCIONES DE UTILIDAD ===
    
    def _show_help(self):
        """Muestra ayuda del asistente"""
        help_text = """
🚀 ASISTENTE RÁPIDO PTZ - AYUDA

CONFIGURACIÓN AUTOMÁTICA:
1. Selecciona una cámara PTZ
2. Ajusta cobertura horizontal y vertical
3. Establece zoom por defecto
4. Haz clic en "Configuración Automática Completa"

CONFIGURACIÓN MANUAL:
1. Haz clic en una celda de la grilla
2. Usa "Posicionar Automáticamente" 
3. Ajusta el zoom con el slider
4. Guarda la configuración de la celda
5. Repite para otras celdas

NAVEGACIÓN:
• Haz clic directo en celdas de la grilla
• Usa botones "Anterior/Siguiente"
• La celda actual se resalta en azul

VISTA PREVIA:
• Activa "Vista Previa en Tiempo Real"
• Las celdas configuradas se muestran en verde
• La cobertura PTZ se visualiza dinámicamente

ZOOM:
• Cerca (20%): Para objetos cercanos
• Medio (40%): Distancia estándar
• Lejos (80%): Para objetos distantes
• Personalizado: Ajusta según necesidades

FINALIZACIÓN:
• "Aplicar y Guardar" confirma la configuración
• Se sobrescribe configuración PTZ existente
• El sistema automático se activa inmediatamente
        """
        
        QMessageBox.information(self.dialog, "❓ Ayuda - Asistente PTZ", help_text)
    
    def _export_configuration(self):
        """Exporta la configuración actual"""
        if not self.cell_configurations:
            QMessageBox.warning(
                self.dialog,
                "Sin Configuración",
                "No hay configuración para exportar."
            )
            return
        
        export_data = {
            "asistente_rapido_config": {
                "version": "1.0",
                "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "ptz_ip": self.current_ptz_ip,
                "grid_size": f"{self.cell_manager.filas}x{self.cell_manager.columnas}",
                "coverage": {
                    "horizontal": self.horizontal_coverage,
                    "vertical": self.vertical_coverage
                },
                "default_zoom": self.default_zoom,
                "cell_configurations": {
                    f"{row},{col}": config 
                    for (row, col), config in self.cell_configurations.items()
                }
            }
        }
        
        # Guardar en ConfigManager
        export_path = f"ptz_config_export_{int(time.time())}.json"
        success = self.config_manager.export_configuration(
            self.config_manager.config_file_path.parent / export_path,
            include_sensitive=False
        )
        
        if success:
            QMessageBox.information(
                self.dialog,
                "✅ Exportación Exitosa",
                f"Configuración exportada a:\n{export_path}"
            )
            self._log_activity(f"📤 Configuración exportada: {export_path}")
        else:
            QMessageBox.warning(
                self.dialog,
                "❌ Error de Exportación",
                "No se pudo exportar la configuración."
            )


class GridPreviewWidget(QWidget):
    """Widget personalizado para vista previa de grilla"""
    
    cell_clicked = pyqtSignal(int, int)  # row, col
    
    def __init__(self, cell_manager, cell_configurations, parent=None):
        super().__init__(parent)
        self.cell_manager = cell_manager
        self.cell_configurations = cell_configurations
        self.selected_cell = None
        self.highlighted_cells = {}  # Para animaciones temporales
        
        # Timer para animaciones
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._update_animations)
        self.animation_timer.start(50)  # 20 FPS
        
        self.setMinimumSize(300, 200)
    
    def set_selected_cell(self, cell_coords):
        """Establece la celda seleccionada"""
        self.selected_cell = cell_coords
        self.update()
    
    def highlight_cell(self, row, col, duration=1000):
        """Resalta una celda temporalmente"""
        self.highlighted_cells[(row, col)] = {
            "start_time": time.time(),
            "duration": duration / 1000.0,
            "intensity": 1.0
        }
    
    def _update_animations(self):
        """Actualiza animaciones"""
        current_time = time.time()
        expired_cells = []
        
        for cell_coords, animation in self.highlighted_cells.items():
            elapsed = current_time - animation["start_time"]
            if elapsed >= animation["duration"]:
                expired_cells.append(cell_coords)
            else:
                # Fade out
                progress = elapsed / animation["duration"]
                animation["intensity"] = 1.0 - progress
        
        # Remover animaciones expiradas
        for cell_coords in expired_cells:
            del self.highlighted_cells[cell_coords]
        
        if self.highlighted_cells:
            self.update()
    
    def mousePressEvent(self, event):
        """Maneja clics en la grilla"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Calcular celda clickeada
            cell_w = self.width() / self.cell_manager.columnas
            cell_h = self.height() / self.cell_manager.filas
            
            col = int(event.position().x() / cell_w)
            row = int(event.position().y() / cell_h)
            
            if (0 <= row < self.cell_manager.filas and 
                0 <= col < self.cell_manager.columnas):
                self.cell_clicked.emit(row, col)
                self.selected_cell = (row, col)
                self.update()
    
    def paintEvent(self, event):
        """Dibuja la vista previa de grilla"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Calcular dimensiones
        cell_w = self.width() / self.cell_manager.columnas
        cell_h = self.height() / self.cell_manager.filas
        
        # Dibujar celdas
        for row in range(self.cell_manager.filas):
            for col in range(self.cell_manager.columnas):
                self._draw_cell(painter, row, col, cell_w, cell_h)
        
        # Dibujar líneas de grilla
        self._draw_grid_lines(painter, cell_w, cell_h)
    
    def _draw_cell(self, painter, row, col, cell_w, cell_h):
        """Dibuja una celda individual"""
        cell_rect = QRectF(col * cell_w, row * cell_h, cell_w, cell_h)
        cell_coords = (row, col)
        
        # Determinar color de celda
        if cell_coords == self.selected_cell:
            # Celda seleccionada
            color = QColor(0, 100, 255, 150)
        elif cell_coords in self.cell_configurations:
            # Celda configurada
            zoom = self.cell_configurations[cell_coords].get("zoom", 0.4)
            intensity = int(zoom * 255)
            color = QColor(0, 200, 0, min(255, max(50, intensity)))
        elif self.cell_manager.is_cell_discarded(row, col):
            # Celda descartada
            color = QColor(200, 0, 0, 100)
        else:
            # Celda normal
            color = QColor(100, 100, 100, 30)
        
        # Aplicar animación si existe
        if cell_coords in self.highlighted_cells:
            animation = self.highlighted_cells[cell_coords]
            intensity = int(255 * animation["intensity"])
            color = QColor(255, 255, 0, intensity)
        
        painter.fillRect(cell_rect, color)
        
        # Dibujar información de zoom si está configurada
        if cell_coords in self.cell_configurations:
            config = self.cell_configurations[cell_coords]
            zoom_percent = int(config.get("zoom", 0) * 100)
            
            painter.setPen(QColor(255, 255, 255))
            font = painter.font()
            font.setPointSize(max(6, int(min(cell_w, cell_h) / 8)))
            painter.setFont(font)
            
            text = f"{zoom_percent}%"
            painter.drawText(cell_rect, Qt.AlignmentFlag.AlignCenter, text)
    
    def _draw_grid_lines(self, painter, cell_w, cell_h):
        """Dibuja líneas de grilla"""
        painter.setPen(QPen(QColor(150, 150, 150, 100), 1))
        
        # Líneas verticales
        for col in range(self.cell_manager.columnas + 1):
            x = col * cell_w
            painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        
        # Líneas horizontales
        for row in range(self.cell_manager.filas + 1):
            y = row * cell_h
            painter.drawLine(QPointF(0, y), QPointF(self.width(), y))