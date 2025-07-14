# gui/components/context_menu.py
"""
Gestión de menús contextuales para la grilla.
Responsabilidades:
- Creación de menús contextuales dinámicos
- Manejo de acciones de menú
- Diálogos de configuración
- Integración con otros managers
- Acciones masivas sobre celdas
"""

from typing import Set, Tuple, Optional, Dict, Any, Callable
from PyQt6.QtWidgets import (QMenu, QAction, QDialog, QVBoxLayout, QHBoxLayout, 
                             QLabel, QComboBox, QLineEdit, QPushButton, QMessageBox,
                             QGroupBox, QFormLayout, QCheckBox, QSpinBox, QWidget)
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QIcon


class ContextMenuManager(QObject):
    """Gestor de menús contextuales para la grilla"""
    
    # Señales
    action_executed = pyqtSignal(str, dict)  # action_name, parameters
    log_message = pyqtSignal(str)  # Mensaje de log
    
    def __init__(self, cell_manager, ptz_manager, parent=None):
        super().__init__(parent)
        self.cell_manager = cell_manager
        self.ptz_manager = ptz_manager
        self.parent_widget = parent
        
        # Estado de funcionalidades especiales
        self.cross_line_enabled = False
        self.adaptive_sampling_available = False
        
        # Cache de acciones para reutilización
        self._action_cache: Dict[str, QAction] = {}
        
    def _emit_log(self, message: str):
        """Emite mensaje de log"""
        self.log_message.emit(message)
        if self.parent_widget and hasattr(self.parent_widget, 'registrar_log'):
            self.parent_widget.registrar_log(message)
    
    # === CREACIÓN DE MENÚS ===
    
    def create_context_menu(self, parent_widget: QWidget, selected_cells: Set[Tuple[int, int]], 
                           click_position: Optional[Tuple[int, int]] = None) -> QMenu:
        """
        Crea menú contextual dinámico basado en el contexto actual
        
        Args:
            parent_widget: Widget padre para el menú
            selected_cells: Celdas actualmente seleccionadas
            click_position: Posición donde se hizo clic (opcional)
        """
        menu = QMenu(parent_widget)
        
        # Configurar estilo del menú
        menu.setStyleSheet("""
            QMenu {
                background-color: #2b2b2b;
                color: white;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 2px;
            }
            QMenu::item:selected {
                background-color: #4a90e2;
            }
            QMenu::separator {
                height: 1px;
                background-color: #555;
                margin: 4px 0px;
            }
        """)
        
        if selected_cells:
            self._add_selection_actions(menu, selected_cells)
        else:
            self._add_general_actions(menu, click_position)
        
        return menu
    
    def _add_selection_actions(self, menu: QMenu, selected_cells: Set[Tuple[int, int]]):
        """Agrega acciones para cuando hay celdas seleccionadas"""
        cell_count = len(selected_cells)
        
        # Sección de información
        info_action = menu.addAction(f"📊 {cell_count} celda(s) seleccionada(s)")
        info_action.setEnabled(False)
        menu.addSeparator()
        
        # Acciones de análisis
        analysis_menu = menu.addMenu("🔍 Análisis")
        
        discard_action = analysis_menu.addAction("❌ Descartar para analíticas")
        discard_action.triggered.connect(lambda: self._handle_discard_cells(selected_cells))
        
        enable_action = analysis_menu.addAction("✅ Habilitar para analíticas")
        enable_action.triggered.connect(lambda: self._handle_enable_cells(selected_cells))
        
        # Acciones de PTZ
        ptz_menu = menu.addMenu("🎯 Control PTZ")
        
        # Submenu de asignación PTZ
        assign_ptz_menu = ptz_menu.addMenu("📍 Asignar PTZ")
        self._populate_ptz_assignment_menu(assign_ptz_menu, selected_cells)
        
        # Acciones rápidas de PTZ
        quick_ptz_action = ptz_menu.addAction("🚀 Asistente Rápido PTZ")
        quick_ptz_action.triggered.connect(self._handle_quick_ptz_setup)
        
        clear_ptz_action = ptz_menu.addAction("🗑️ Quitar PTZ")
        clear_ptz_action.triggered.connect(lambda: self._handle_clear_ptz_mapping(selected_cells))
        
        # Acciones de presets
        preset_menu = menu.addMenu("📍 Presets")
        
        set_preset_action = preset_menu.addAction("➕ Asignar preset...")
        set_preset_action.triggered.connect(lambda: self._handle_set_preset(selected_cells))
        
        clear_preset_action = preset_menu.addAction("➖ Quitar preset")
        clear_preset_action.triggered.connect(lambda: self._handle_clear_preset(selected_cells))
        
        # Presets rápidos
        preset_menu.addSeparator()
        for i in range(1, 6):
            quick_preset_action = preset_menu.addAction(f"🔢 Preset {i}")
            quick_preset_action.triggered.connect(lambda checked, p=i: self._handle_quick_preset(selected_cells, str(p)))
        
        # Acciones de selección
        menu.addSeparator()
        selection_menu = menu.addMenu("📋 Selección")
        
        clear_selection_action = selection_menu.addAction("🗑️ Limpiar selección")
        clear_selection_action.triggered.connect(self._handle_clear_selection)
        
        invert_selection_action = selection_menu.addAction("🔄 Invertir selección")
        invert_selection_action.triggered.connect(self._handle_invert_selection)
        
        select_all_action = selection_menu.addAction("🎯 Seleccionar todo")
        select_all_action.triggered.connect(self._handle_select_all)
    
    def _add_general_actions(self, menu: QMenu, click_position: Optional[Tuple[int, int]]):
        """Agrega acciones generales cuando no hay selección"""
        # Acciones de selección
        select_menu = menu.addMenu("📋 Selección")
        
        select_all_action = select_menu.addAction("🎯 Seleccionar todas las celdas")
        select_all_action.triggered.connect(self._handle_select_all)
        
        select_ptz_action = select_menu.addAction("🎯 Seleccionar celdas con PTZ")
        select_ptz_action.triggered.connect(self._handle_select_ptz_cells)
        
        select_preset_action = select_menu.addAction("📍 Seleccionar celdas con preset")
        select_preset_action.triggered.connect(self._handle_select_preset_cells)
        
        # Configuración global
        menu.addSeparator()
        config_menu = menu.addMenu("⚙️ Configuración")
        
        ptz_config_action = config_menu.addAction("🎯 Configurar PTZ Global")
        ptz_config_action.triggered.connect(self._handle_global_ptz_config)
        
        grid_config_action = config_menu.addAction("📐 Configurar Grilla")
        grid_config_action.triggered.connect(self._handle_grid_config)
        
        # Línea de conteo
        menu.addSeparator()
        if hasattr(self.parent_widget, 'cross_line_enabled'):
            if self.parent_widget.cross_line_enabled:
                disable_line_action = menu.addAction("➖ Desactivar línea de conteo")
                disable_line_action.triggered.connect(self._handle_disable_cross_line)
            else:
                enable_line_action = menu.addAction("➕ Activar línea de conteo")
                enable_line_action.triggered.connect(self._handle_enable_cross_line)
        
        # Muestreo adaptativo si está disponible
        if self.adaptive_sampling_available:
            sampling_menu = menu.addMenu("🧠 Muestreo Adaptativo")
            self._add_adaptive_sampling_actions(sampling_menu)
    
    def _populate_ptz_assignment_menu(self, menu: QMenu, selected_cells: Set[Tuple[int, int]]):
        """Popula el submenu de asignación PTZ"""
        ptz_cameras = self.ptz_manager.get_ptz_cameras()
        
        if not ptz_cameras:
            no_ptz_action = menu.addAction("❌ No hay cámaras PTZ")
            no_ptz_action.setEnabled(False)
            return
        
        for ptz_ip in ptz_cameras:
            ptz_info = self.ptz_manager.get_camera_info(ptz_ip)
            display_text = f"🎯 {ptz_ip}"
            if ptz_info:
                usuario = ptz_info.get('usuario', 'admin')
                display_text += f" ({usuario})"
            
            ptz_action = menu.addAction(display_text)
            ptz_action.triggered.connect(lambda checked, ip=ptz_ip: self._handle_assign_ptz(selected_cells, ip))
    
    def _add_adaptive_sampling_actions(self, menu: QMenu):
        """Agrega acciones de muestreo adaptativo"""
        enable_action = menu.addAction("✅ Habilitar muestreo adaptativo")
        enable_action.triggered.connect(self._handle_enable_adaptive_sampling)
        
        config_action = menu.addAction("⚙️ Configurar muestreo")
        config_action.triggered.connect(self._handle_configure_adaptive_sampling)
        
        reset_action = menu.addAction("🔄 Resetear estadísticas")
        reset_action.triggered.connect(self._handle_reset_adaptive_stats)
    
    # === MANEJADORES DE ACCIONES ===
    
    def _handle_discard_cells(self, selected_cells: Set[Tuple[int, int]]):
        """Maneja el descarte de celdas"""
        count = self.cell_manager.discard_selected_cells()
        self._emit_log(f"🚫 {count} celdas descartadas para análisis")
        self.action_executed.emit("discard_cells", {"count": count})
    
    def _handle_enable_cells(self, selected_cells: Set[Tuple[int, int]]):
        """Maneja la habilitación de celdas descartadas"""
        count = 0
        for row, col in selected_cells:
            if self.cell_manager.undiscard_cell(row, col):
                count += 1
        
        self._emit_log(f"✅ {count} celdas habilitadas para análisis")
        self.action_executed.emit("enable_cells", {"count": count})
    
    def _handle_assign_ptz(self, selected_cells: Set[Tuple[int, int]], ptz_ip: str):
        """Maneja la asignación de PTZ a celdas"""
        dialog = PTZAssignmentDialog(self.parent_widget, ptz_ip, selected_cells, self.ptz_manager)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            config = dialog.get_configuration()
            count = self.cell_manager.set_selected_cells_ptz_mapping(config)
            self._emit_log(f"🎯 PTZ {ptz_ip} asignado a {count} celdas")
            self.action_executed.emit("assign_ptz", {"ip": ptz_ip, "count": count, "config": config})
    
    def _handle_clear_ptz_mapping(self, selected_cells: Set[Tuple[int, int]]):
        """Maneja la limpieza de mapping PTZ"""
        count = self.cell_manager.clear_selected_cells_ptz_mapping()
        self._emit_log(f"🗑️ Mapping PTZ removido de {count} celdas")
        self.action_executed.emit("clear_ptz", {"count": count})
    
    def _handle_set_preset(self, selected_cells: Set[Tuple[int, int]]):
        """Maneja la asignación de preset"""
        dialog = PresetAssignmentDialog(self.parent_widget, selected_cells)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            preset = dialog.get_preset()
            count = self.cell_manager.set_selected_cells_preset(preset)
            self._emit_log(f"📍 Preset {preset} asignado a {count} celdas")
            self.action_executed.emit("set_preset", {"preset": preset, "count": count})
    
    def _handle_clear_preset(self, selected_cells: Set[Tuple[int, int]]):
        """Maneja la limpieza de presets"""
        count = self.cell_manager.clear_selected_cells_preset()
        self._emit_log(f"🗑️ Presets removidos de {count} celdas")
        self.action_executed.emit("clear_preset", {"count": count})
    
    def _handle_quick_preset(self, selected_cells: Set[Tuple[int, int]], preset: str):
        """Maneja asignación rápida de preset"""
        count = self.cell_manager.set_selected_cells_preset(preset)
        self._emit_log(f"🔢 Preset {preset} asignado rápidamente a {count} celdas")
        self.action_executed.emit("quick_preset", {"preset": preset, "count": count})
    
    def _handle_clear_selection(self):
        """Maneja la limpieza de selección"""
        count = self.cell_manager.clear_selection()
        self._emit_log(f"🗑️ Selección limpiada ({count} celdas)")
        self.action_executed.emit("clear_selection", {"count": count})
    
    def _handle_select_all(self):
        """Maneja la selección de todas las celdas"""
        count = self.cell_manager.select_all_cells()
        self._emit_log(f"🎯 Todas las celdas seleccionadas ({count} celdas)")
        self.action_executed.emit("select_all", {"count": count})
    
    def _handle_invert_selection(self):
        """Maneja la inversión de selección"""
        # Obtener todas las celdas
        all_cells = {(row, col) for row in range(self.cell_manager.filas) 
                                for col in range(self.cell_manager.columnas)}
        
        # Calcular nueva selección (invertida)
        current_selection = self.cell_manager.selected_cells.copy()
        new_selection = all_cells - current_selection
        
        # Aplicar nueva selección
        self.cell_manager.clear_selection()
        count = self.cell_manager.select_multiple_cells(new_selection)
        
        self._emit_log(f"🔄 Selección invertida ({count} celdas ahora seleccionadas)")
        self.action_executed.emit("invert_selection", {"count": count})
    
    def _handle_select_ptz_cells(self):
        """Selecciona todas las celdas con PTZ configurado"""
        ptz_cells = self.cell_manager.get_cells_by_state("with_ptz")
        count = self.cell_manager.select_multiple_cells(ptz_cells)
        self._emit_log(f"🎯 {count} celdas con PTZ seleccionadas")
        self.action_executed.emit("select_ptz_cells", {"count": count})
    
    def _handle_select_preset_cells(self):
        """Selecciona todas las celdas con preset"""
        preset_cells = self.cell_manager.get_cells_by_state("with_presets")
        count = self.cell_manager.select_multiple_cells(preset_cells)
        self._emit_log(f"📍 {count} celdas con preset seleccionadas")
        self.action_executed.emit("select_preset_cells", {"count": count})
    
    def _handle_quick_ptz_setup(self):
        """Maneja el asistente rápido PTZ"""
        try:
            from gui.components.asistente_rapido import AsistenteRapidoPTZ
            asistente = AsistenteRapidoPTZ(self.parent_widget)
            asistente.show_asistente_rapido()
            self.action_executed.emit("quick_ptz_setup", {})
        except ImportError:
            QMessageBox.warning(
                self.parent_widget, 
                "Módulo no disponible",
                "El Asistente Rápido PTZ no está disponible."
            )
    
    def _handle_global_ptz_config(self):
        """Maneja la configuración global de PTZ"""
        dialog = GlobalPTZConfigDialog(self.parent_widget, self.ptz_manager)
        dialog.exec()
    
    def _handle_grid_config(self):
        """Maneja la configuración de grilla"""
        dialog = GridConfigDialog(self.parent_widget, self.cell_manager)
        dialog.exec()
    
    def _handle_enable_cross_line(self):
        """Habilita línea de conteo"""
        if hasattr(self.parent_widget, 'start_line_edit'):
            self.parent_widget.start_line_edit()
            self.action_executed.emit("enable_cross_line", {})
    
    def _handle_disable_cross_line(self):
        """Deshabilita línea de conteo"""
        if hasattr(self.parent_widget, 'disable_cross_line'):
            self.parent_widget.disable_cross_line()
            self.action_executed.emit("disable_cross_line", {})
    
    def _handle_enable_adaptive_sampling(self):
        """Habilita muestreo adaptativo"""
        # Implementar según disponibilidad del módulo
        self.action_executed.emit("enable_adaptive_sampling", {})
    
    def _handle_configure_adaptive_sampling(self):
        """Configura muestreo adaptativo"""
        # Implementar diálogo de configuración
        self.action_executed.emit("configure_adaptive_sampling", {})
    
    def _handle_reset_adaptive_stats(self):
        """Resetea estadísticas adaptativas"""
        # Implementar reset de estadísticas
        self.action_executed.emit("reset_adaptive_stats", {})


# === DIÁLOGOS ESPECIALIZADOS ===

class PTZAssignmentDialog(QDialog):
    """Diálogo para asignación de PTZ a celdas"""
    
    def __init__(self, parent, ptz_ip: str, selected_cells: Set[Tuple[int, int]], ptz_manager):
        super().__init__(parent)
        self.ptz_ip = ptz_ip
        self.selected_cells = selected_cells
        self.ptz_manager = ptz_manager
        
        self.setWindowTitle(f"🎯 Asignar PTZ {ptz_ip}")
        self.setMinimumSize(400, 300)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Información
        info_label = QLabel(f"Configurando PTZ {self.ptz_ip} para {len(self.selected_cells)} celda(s)")
        info_label.setStyleSheet("font-weight: bold; color: #2E5BBA; margin-bottom: 10px;")
        layout.addWidget(info_label)
        
        # Tipo de configuración
        type_group = QGroupBox("Tipo de Control PTZ")
        type_layout = QVBoxLayout()
        
        self.preset_radio = QCheckBox("🔢 Usar Preset")
        self.absolute_radio = QCheckBox("📐 Posición Absoluta (Recomendado)")
        self.absolute_radio.setChecked(True)
        
        type_layout.addWidget(self.absolute_radio)
        type_layout.addWidget(self.preset_radio)
        type_group.setLayout(type_layout)
        layout.addWidget(type_group)
        
        # Configuración de preset
        self.preset_group = QGroupBox("Configuración de Preset")
        preset_layout = QFormLayout()
        
        self.preset_edit = QLineEdit()
        self.preset_edit.setPlaceholderText("Ej: 1, 2, 3...")
        preset_layout.addRow("Número de preset:", self.preset_edit)
        
        self.preset_group.setLayout(preset_layout)
        self.preset_group.setEnabled(False)
        layout.addWidget(self.preset_group)
        
        # Configuración absoluta
        self.absolute_group = QGroupBox("Configuración Absoluta")
        absolute_layout = QFormLayout()
        
        self.auto_calculate_check = QCheckBox("Calcular posiciones automáticamente")
        self.auto_calculate_check.setChecked(True)
        
        self.default_zoom_spin = QSpinBox()
        self.default_zoom_spin.setRange(10, 100)
        self.default_zoom_spin.setValue(40)
        self.default_zoom_spin.setSuffix("%")
        
        absolute_layout.addRow("", self.auto_calculate_check)
        absolute_layout.addRow("Zoom por defecto:", self.default_zoom_spin)
        
        self.absolute_group.setLayout(absolute_layout)
        layout.addWidget(self.absolute_group)
        
        # Botones
        button_layout = QHBoxLayout()
        
        self.test_btn = QPushButton("🧪 Probar Conexión")
        self.ok_btn = QPushButton("✅ Aplicar")
        self.cancel_btn = QPushButton("❌ Cancelar")
        
        button_layout.addWidget(self.test_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.ok_btn)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
        
        # Conectar señales
        self.preset_radio.toggled.connect(self.preset_group.setEnabled)
        self.absolute_radio.toggled.connect(self.absolute_group.setEnabled)
        self.test_btn.clicked.connect(self._test_connection)
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
    
    def _test_connection(self):
        """Prueba la conexión PTZ"""
        success = self.ptz_manager.test_ptz_connection(self.ptz_ip)
        if success:
            QMessageBox.information(self, "✅ Conexión Exitosa", f"PTZ {self.ptz_ip} responde correctamente")
        else:
            QMessageBox.warning(self, "❌ Error de Conexión", f"No se pudo conectar con PTZ {self.ptz_ip}")
    
    def get_configuration(self) -> Dict[str, Any]:
        """Obtiene la configuración seleccionada"""
        if self.preset_radio.isChecked():
            return {
                "ip": self.ptz_ip,
                "type": "preset",
                "preset": self.preset_edit.text().strip()
            }
        else:
            return {
                "ip": self.ptz_ip,
                "type": "absolute_with_zoom",
                "auto_calculate": self.auto_calculate_check.isChecked(),
                "default_zoom": self.default_zoom_spin.value() / 100.0
            }


class PresetAssignmentDialog(QDialog):
    """Diálogo para asignación de preset"""
    
    def __init__(self, parent, selected_cells: Set[Tuple[int, int]]):
        super().__init__(parent)
        self.selected_cells = selected_cells
        
        self.setWindowTitle("📍 Asignar Preset")
        self.setMinimumSize(300, 150)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        info_label = QLabel(f"Asignar preset a {len(self.selected_cells)} celda(s)")
        layout.addWidget(info_label)
        
        form_layout = QFormLayout()
        
        self.preset_edit = QLineEdit()
        self.preset_edit.setPlaceholderText("Ej: 1, 2, 3...")
        form_layout.addRow("Número de preset:", self.preset_edit)
        
        layout.addLayout(form_layout)
        
        # Botones
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("✅ Asignar")
        cancel_btn = QPushButton("❌ Cancelar")
        
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
    
    def get_preset(self) -> str:
        """Obtiene el preset ingresado"""
        return self.preset_edit.text().strip()


class GlobalPTZConfigDialog(QDialog):
    """Diálogo para configuración global de PTZ"""
    
    def __init__(self, parent, ptz_manager):
        super().__init__(parent)
        self.ptz_manager = ptz_manager
        
        self.setWindowTitle("⚙️ Configuración Global PTZ")
        self.setMinimumSize(500, 400)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Estadísticas PTZ
        stats_group = QGroupBox("📊 Estado del Sistema PTZ")
        stats_layout = QFormLayout()
        
        stats = self.ptz_manager.get_statistics()
        stats_layout.addRow("Cámaras PTZ:", QLabel(str(stats["total_ptz_cameras"])))
        stats_layout.addRow("Conectadas:", QLabel(str(stats["connected_ptz_cameras"])))
        stats_layout.addRow("Auto-trigger:", QLabel("✅ Habilitado" if stats["auto_trigger_enabled"] else "❌ Deshabilitado"))
        
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)
        
        # Configuración
        config_group = QGroupBox("⚙️ Configuración")
        config_layout = QFormLayout()
        
        self.auto_trigger_check = QCheckBox("Habilitar trigger automático")
        self.auto_trigger_check.setChecked(stats["auto_trigger_enabled"])
        
        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setRange(1, 10)
        self.cooldown_spin.setValue(int(stats["ptz_cooldown"]))
        self.cooldown_spin.setSuffix(" segundos")
        
        config_layout.addRow("", self.auto_trigger_check)
        config_layout.addRow("Cooldown entre movimientos:", self.cooldown_spin)
        
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)
        
        # Botones
        button_layout = QHBoxLayout()
        apply_btn = QPushButton("✅ Aplicar")
        close_btn = QPushButton("❌ Cerrar")
        
        button_layout.addWidget(apply_btn)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)
        
        apply_btn.clicked.connect(self._apply_config)
        close_btn.clicked.connect(self.close)
    
    def _apply_config(self):
        """Aplica la configuración"""
        self.ptz_manager.set_auto_trigger_enabled(self.auto_trigger_check.isChecked())
        self.ptz_manager.set_ptz_cooldown(self.cooldown_spin.value())
        
        QMessageBox.information(self, "✅ Configuración Aplicada", "La configuración PTZ ha sido actualizada")


class GridConfigDialog(QDialog):
    """Diálogo para configuración de grilla"""
    
    def __init__(self, parent, cell_manager):
        super().__init__(parent)
        self.cell_manager = cell_manager
        
        self.setWindowTitle("📐 Configuración de Grilla")
        self.setMinimumSize(400, 300)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Estadísticas
        stats_group = QGroupBox("📊 Estadísticas de Grilla")
        stats_layout = QFormLayout()
        
        stats = self.cell_manager.get_statistics()
        stats_layout.addRow("Total de celdas:", QLabel(str(stats["total_cells"])))
        stats_layout.addRow("Seleccionadas:", QLabel(str(stats["selected_cells"])))
        stats_layout.addRow("Descartadas:", QLabel(str(stats["discarded_cells"])))
        stats_layout.addRow("Con PTZ:", QLabel(str(stats["cells_with_ptz"])))
        stats_layout.addRow("Con presets:", QLabel(str(stats["cells_with_presets"])))
        
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)
        
        # Acciones masivas
        actions_group = QGroupBox("🔧 Acciones Masivas")
        actions_layout = QVBoxLayout()
        
        reset_all_btn = QPushButton("🗑️ Resetear Todo")
        reset_all_btn.clicked.connect(self._reset_all)
        
        clear_discarded_btn = QPushButton("✅ Limpiar Celdas Descartadas")
        clear_discarded_btn.clicked.connect(self._clear_discarded)
        
        clear_ptz_btn = QPushButton("🎯 Limpiar Todas las PTZ")
        clear_ptz_btn.clicked.connect(self._clear_all_ptz)
        
        clear_presets_btn = QPushButton("📍 Limpiar Todos los Presets")
        clear_presets_btn.clicked.connect(self._clear_all_presets)
        
        actions_layout.addWidget(reset_all_btn)
        actions_layout.addWidget(clear_discarded_btn)
        actions_layout.addWidget(clear_ptz_btn)
        actions_layout.addWidget(clear_presets_btn)
        
        actions_group.setLayout(actions_layout)
        layout.addWidget(actions_group)
        
        # Botones
        button_layout = QHBoxLayout()
        close_btn = QPushButton("❌ Cerrar")
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)
        
        close_btn.clicked.connect(self.close)
    
    def _reset_all(self):
        """Resetea todos los estados de celdas"""
        reply = QMessageBox.question(
            self, 
            "Confirmar Reset",
            "¿Estás seguro de que quieres resetear TODOS los estados de celdas?\n"
            "Esto eliminará:\n"
            "• Todas las selecciones\n"
            "• Todas las celdas descartadas\n"
            "• Todos los presets\n"
            "• Todas las configuraciones PTZ",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.cell_manager.reset_all_states()
            QMessageBox.information(self, "✅ Reset Completo", "Todos los estados han sido reseteados")
    
    def _clear_discarded(self):
        """Limpia todas las celdas descartadas"""
        count = self.cell_manager.enable_discarded_cells()
        QMessageBox.information(self, "✅ Limpieza Completa", f"{count} celdas descartadas han sido habilitadas")
    
    def _clear_all_ptz(self):
        """Limpia todas las configuraciones PTZ"""
        reply = QMessageBox.question(
            self, 
            "Confirmar Limpieza PTZ",
            "¿Estás seguro de que quieres eliminar TODAS las configuraciones PTZ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.cell_manager.cell_ptz_map.clear()
            self.cell_manager.cells_changed.emit()
            QMessageBox.information(self, "✅ PTZ Limpiado", "Todas las configuraciones PTZ han sido eliminadas")
    
    def _clear_all_presets(self):
        """Limpia todos los presets"""
        reply = QMessageBox.question(
            self, 
            "Confirmar Limpieza Presets",
            "¿Estás seguro de que quieres eliminar TODOS los presets?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.cell_manager.cell_presets.clear()
            self.cell_manager.cells_changed.emit()
            QMessageBox.information(self, "✅ Presets Limpiados", "Todos los presets han sido eliminados")