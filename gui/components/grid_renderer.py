# gui/components/grid_renderer.py
"""
Renderizado y dibujado de la grilla de celdas.
Responsabilidades:
- Dibujado de grilla con estados de celdas
- Renderizado de overlays (presets, PTZ, etc.)
- Gestión de colores y estilos
- Optimización de rendering
- Efectos visuales y animaciones
"""

import time
from typing import Dict, Any, Optional, Tuple, List
from PyQt6.QtCore import QObject, QRectF, QPointF, QSizeF, Qt, QTimer
from PyQt6.QtGui import (QPainter, QPen, QColor, QBrush, QFont, QPixmap, 
                         QLinearGradient, QRadialGradient, QPainterPath)
from PyQt6.QtWidgets import QWidget


class GridRenderer(QObject):
    """Renderizador de grilla con estados visuales"""
    
    def __init__(self, cell_manager, parent=None):
        super().__init__(parent)
        self.cell_manager = cell_manager
        self.parent_widget = parent
        
        # Configuración de colores
        self.colors = {
            # Estados básicos de celdas
            "selected": QColor(255, 0, 0, 100),          # Rojo transparente
            "discarded": QColor(200, 0, 0, 150),         # Rojo sólido
            "temporal": QColor(0, 255, 0, 100),          # Verde transparente
            "preset": QColor(0, 0, 255, 80),             # Azul transparente
            "ptz_mapped": QColor(128, 0, 128, 80),       # Morado transparente
            "area_active": QColor(255, 165, 0, 100),     # Naranja transparente
            
            # Colores de grilla
            "grid_lines": QColor(80, 80, 80, 120),       # Gris transparente
            "border": QColor(255, 255, 255, 180),        # Blanco semi-transparente
            
            # Colores de texto
            "text_preset": QColor(255, 255, 255),        # Blanco
            "text_ptz": QColor(255, 255, 0),             # Amarillo
            "text_info": QColor(200, 200, 200),          # Gris claro
            
            # Efectos especiales
            "highlight": QColor(255, 255, 255, 50),      # Highlight suave
            "animation": QColor(0, 255, 255, 100),       # Cian para animaciones
        }
        
        # Configuración de estilos
        self.styles = {
            "grid_line_width": 1,
            "border_width": 2,
            "text_size": 8,
            "text_size_large": 10,
            "corner_radius": 0,  # Radio para esquinas redondeadas
            "shadow_enabled": False,
            "gradient_enabled": True,
            "animation_enabled": True
        }
        
        # Cache de rendering
        self._grid_lines_cache: Optional[QPixmap] = None
        self._cache_size: Optional[QSizeF] = None
        self._cache_grid_size: Optional[Tuple[int, int]] = None
        
        # Estado de animaciones
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._update_animations)
        self.animation_frame = 0
        self.animated_cells: Dict[Tuple[int, int], Dict[str, Any]] = {}
        
        # Configuración de información adaptativa
        self.adaptive_info_enabled = False
        self.show_statistics = False
        self.info_position = "top_right"  # top_right, top_left, bottom_right, bottom_left
    
    # === CONFIGURACIÓN ===
    
    def set_color(self, element: str, color: QColor):
        """Establece color para un elemento específico"""
        self.colors[element] = color
        self._invalidate_cache()
    
    def set_style(self, property_name: str, value: Any):
        """Establece una propiedad de estilo"""
        self.styles[property_name] = value
        self._invalidate_cache()
    
    def enable_animations(self, enabled: bool):
        """Habilita/deshabilita animaciones"""
        self.styles["animation_enabled"] = enabled
        if enabled:
            self.animation_timer.start(50)  # 20 FPS
        else:
            self.animation_timer.stop()
            self.animated_cells.clear()
    
    def enable_adaptive_info(self, enabled: bool):
        """Habilita información adaptativa en pantalla"""
        self.adaptive_info_enabled = enabled
    
    def set_info_position(self, position: str):
        """Establece posición de la información en pantalla"""
        valid_positions = ["top_right", "top_left", "bottom_right", "bottom_left"]
        if position in valid_positions:
            self.info_position = position
    
    # === RENDERIZADO PRINCIPAL ===
    
    def paint_grid(self, painter: QPainter, widget_rect: QRectF, 
                   video_pixmap: Optional[QPixmap] = None):
        """
        Renderiza la grilla completa
        
        Args:
            painter: QPainter configurado
            widget_rect: Rectángulo del widget
            video_pixmap: Pixmap del video de fondo (opcional)
        """
        # Configurar antialiasing
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        
        # Dibujar video de fondo si está disponible
        if video_pixmap and not video_pixmap.isNull():
            self._paint_video_background(painter, widget_rect, video_pixmap)
        else:
            # Dibujar fondo negro si no hay video
            painter.fillRect(widget_rect, QColor("black"))
            painter.setPen(QColor("white"))
            painter.drawText(widget_rect, Qt.AlignmentFlag.AlignCenter, "Sin señal")
        
        # Calcular dimensiones de celdas
        cell_w = widget_rect.width() / self.cell_manager.columnas
        cell_h = widget_rect.height() / self.cell_manager.filas
        
        # Dibujar celdas
        self._paint_cells(painter, widget_rect, cell_w, cell_h)
        
        # Dibujar líneas de grilla
        self._paint_grid_lines(painter, widget_rect, cell_w, cell_h)
        
        # Dibujar overlays (presets, PTZ, etc.)
        self._paint_overlays(painter, widget_rect, cell_w, cell_h)
        
        # Dibujar información adaptativa
        if self.adaptive_info_enabled:
            self._paint_adaptive_info(painter, widget_rect)
        
        # Dibujar efectos especiales
        if self.styles["animation_enabled"]:
            self._paint_animations(painter, widget_rect, cell_w, cell_h)
    
    def _paint_video_background(self, painter: QPainter, widget_rect: QRectF, video_pixmap: QPixmap):
        """Dibuja el video de fondo manteniendo aspect ratio"""
        # Calcular rectángulo escalado manteniendo aspect ratio
        pixmap_size = QSizeF(video_pixmap.size())
        scaled_size = pixmap_size.scaled(widget_rect.size(), Qt.AspectRatioMode.KeepAspectRatio)
        
        # Centrar el video
        video_rect = QRectF()
        video_rect.setSize(scaled_size)
        video_rect.moveCenter(widget_rect.center())
        
        # Dibujar video
        painter.drawPixmap(video_rect, video_pixmap, QRectF(video_pixmap.rect()))
    
    def _paint_cells(self, painter: QPainter, widget_rect: QRectF, cell_w: float, cell_h: float):
        """Dibuja todas las celdas con sus estados"""
        for row in range(self.cell_manager.filas):
            for col in range(self.cell_manager.columnas):
                cell_rect = QRectF(col * cell_w, row * cell_h, cell_w, cell_h)
                self._paint_single_cell(painter, row, col, cell_rect)
    
    def _paint_single_cell(self, painter: QPainter, row: int, col: int, cell_rect: QRectF):
        """Dibuja una celda individual con su estado"""
        # Obtener color de la celda según su estado
        cell_color = self._get_cell_color(row, col)
        
        if cell_color:
            # Aplicar gradiente si está habilitado
            if self.styles["gradient_enabled"]:
                brush = self._create_gradient_brush(cell_color, cell_rect)
            else:
                brush = QBrush(cell_color)
            
            # Dibujar rectángulo de celda
            if self.styles["corner_radius"] > 0:
                painter.setBrush(brush)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(cell_rect, self.styles["corner_radius"], self.styles["corner_radius"])
            else:
                painter.fillRect(cell_rect, brush)
            
            # Dibujar sombra si está habilitada
            if self.styles["shadow_enabled"]:
                self._paint_cell_shadow(painter, cell_rect)
    
    def _get_cell_color(self, row: int, col: int) -> Optional[QColor]:
        """Determina el color de una celda basado en su estado"""
        # Prioridad de estados (el primero que coincida determina el color)
        if self.cell_manager.is_cell_discarded(row, col):
            return self.colors["discarded"]
        elif self.cell_manager.has_cell_preset(row, col):
            return self.colors["preset"]
        elif self.cell_manager.has_cell_ptz_mapping(row, col):
            return self.colors["ptz_mapped"]
        elif self.cell_manager.is_cell_selected(row, col):
            return self.colors["selected"]
        elif self.cell_manager.is_cell_temporal(row, col):
            return self.colors["temporal"]
        elif self._is_area_active(row, col):
            return self.colors["area_active"]
        
        return None
    
    def _is_area_active(self, row: int, col: int) -> bool:
        """Verifica si el área está activa (compatibilidad con sistema anterior)"""
        try:
            index = self.cell_manager.get_cell_index(row, col)
            return (index < len(self.cell_manager.area) and 
                   self.cell_manager.area[index] == 1)
        except:
            return False
    
    def _create_gradient_brush(self, base_color: QColor, rect: QRectF) -> QBrush:
        """Crea un brush con gradiente"""
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        
        # Color más claro en la parte superior
        light_color = QColor(base_color)
        light_color.setAlpha(int(base_color.alpha() * 0.7))
        
        # Color más oscuro en la parte inferior
        dark_color = QColor(base_color)
        dark_color.setAlpha(int(base_color.alpha() * 1.3))
        
        gradient.setColorAt(0, light_color)
        gradient.setColorAt(1, dark_color)
        
        return QBrush(gradient)
    
    def _paint_cell_shadow(self, painter: QPainter, cell_rect: QRectF):
        """Dibuja sombra para una celda"""
        shadow_rect = cell_rect.adjusted(2, 2, 2, 2)
        shadow_color = QColor(0, 0, 0, 50)
        painter.fillRect(shadow_rect, shadow_color)
    
    def _paint_grid_lines(self, painter: QPainter, widget_rect: QRectF, cell_w: float, cell_h: float):
        """Dibuja las líneas de la grilla"""
        # Usar cache si está disponible y es válido
        current_size = widget_rect.size()
        current_grid = (self.cell_manager.filas, self.cell_manager.columnas)
        
        if (self._grid_lines_cache and 
            self._cache_size == current_size and 
            self._cache_grid_size == current_grid):
            painter.drawPixmap(widget_rect.topLeft(), self._grid_lines_cache)
            return
        
        # Crear cache de líneas de grilla
        self._create_grid_lines_cache(current_size, current_grid, cell_w, cell_h)
        
        # Dibujar desde cache
        if self._grid_lines_cache:
            painter.drawPixmap(widget_rect.topLeft(), self._grid_lines_cache)
    
    def _create_grid_lines_cache(self, size: QSizeF, grid_size: Tuple[int, int], 
                                cell_w: float, cell_h: float):
        """Crea cache de líneas de grilla"""
        self._grid_lines_cache = QPixmap(int(size.width()), int(size.height()))
        self._grid_lines_cache.fill(Qt.GlobalColor.transparent)
        
        cache_painter = QPainter(self._grid_lines_cache)
        cache_painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        
        # Configurar pen para líneas de grilla
        pen = QPen(self.colors["grid_lines"])
        pen.setWidth(self.styles["grid_line_width"])
        cache_painter.setPen(pen)
        
        filas, columnas = grid_size
        
        # Líneas verticales
        for col in range(columnas + 1):
            x = col * cell_w
            cache_painter.drawLine(QPointF(x, 0), QPointF(x, size.height()))
        
        # Líneas horizontales
        for row in range(filas + 1):
            y = row * cell_h
            cache_painter.drawLine(QPointF(0, y), QPointF(size.width(), y))
        
        cache_painter.end()
        
        # Actualizar información de cache
        self._cache_size = size
        self._cache_grid_size = grid_size
    
    def _paint_overlays(self, painter: QPainter, widget_rect: QRectF, cell_w: float, cell_h: float):
        """Dibuja overlays de información (presets, PTZ, etc.)"""
        for row in range(self.cell_manager.filas):
            for col in range(self.cell_manager.columnas):
                cell_rect = QRectF(col * cell_w, row * cell_h, cell_w, cell_h)
                
                # Dibujar preset local
                self._paint_preset_overlay(painter, row, col, cell_rect)
                
                # Dibujar información PTZ
                self._paint_ptz_overlay(painter, row, col, cell_rect)
                
                # Dibujar información adicional si hay espacio
                if cell_w > 50 and cell_h > 30:  # Solo si la celda es suficientemente grande
                    self._paint_cell_info(painter, row, col, cell_rect)
    
    def _paint_preset_overlay(self, painter: QPainter, row: int, col: int, cell_rect: QRectF):
        """Dibuja overlay de preset local"""
        preset = self.cell_manager.get_cell_preset(row, col)
        if not preset:
            return
        
        # Configurar texto
        painter.setPen(self.colors["text_preset"])
        font = painter.font()
        font.setPointSize(self.styles["text_size"])
        font.setBold(True)
        painter.setFont(font)
        
        # Dibujar texto de preset
        preset_text = f"P{preset}"
        text_rect = painter.fontMetrics().boundingRect(preset_text)
        
        # Posición en esquina superior izquierda
        text_pos = QPointF(
            cell_rect.left() + 2,
            cell_rect.top() + text_rect.height() + 2
        )
        
        painter.drawText(text_pos, preset_text)
    
    def _paint_ptz_overlay(self, painter: QPainter, row: int, col: int, cell_rect: QRectF):
        """Dibuja overlay de información PTZ"""
        ptz_mapping = self.cell_manager.get_cell_ptz_mapping(row, col)
        if not ptz_mapping:
            return
        
        # Configurar texto
        painter.setPen(self.colors["text_ptz"])
        font = painter.font()
        font.setPointSize(self.styles["text_size"])
        painter.setFont(font)
        
        # Determinar texto a mostrar
        if ptz_mapping.get("type") == "preset":
            display_text = str(ptz_mapping.get("preset", "?"))
        elif ptz_mapping.get("type") in ["absolute", "absolute_with_zoom"]:
            zoom = ptz_mapping.get("zoom", 0)
            display_text = f"{zoom*100:.0f}%" if zoom else "ABS"
        else:
            display_text = "PTZ"
        
        # Calcular posición (esquina superior derecha)
        text_rect = painter.fontMetrics().boundingRect(display_text)
        text_pos = QPointF(
            cell_rect.right() - text_rect.width() - 2,
            cell_rect.top() + text_rect.height() + 2
        )
        
        painter.drawText(text_pos, display_text)
    
    def _paint_cell_info(self, painter: QPainter, row: int, col: int, cell_rect: QRectF):
        """Dibuja información adicional de la celda si hay espacio"""
        if not self.show_statistics:
            return
        
        # Información del estado de la celda
        state_info = []
        
        if self.cell_manager.is_cell_selected(row, col):
            state_info.append("SEL")
        if self.cell_manager.is_cell_discarded(row, col):
            state_info.append("DESC")
        if self.cell_manager.is_cell_temporal(row, col):
            state_info.append("TEMP")
        
        if not state_info:
            return
        
        # Configurar texto pequeño
        painter.setPen(self.colors["text_info"])
        font = painter.font()
        font.setPointSize(self.styles["text_size"] - 1)
        painter.setFont(font)
        
        # Dibujar en la parte inferior de la celda
        info_text = " ".join(state_info)
        text_rect = painter.fontMetrics().boundingRect(info_text)
        text_pos = QPointF(
            cell_rect.center().x() - text_rect.width() / 2,
            cell_rect.bottom() - 2
        )
        
        painter.drawText(text_pos, info_text)
    
    def _paint_adaptive_info(self, painter: QPainter, widget_rect: QRectF):
        """Dibuja información adaptativa en pantalla"""
        # Obtener estadísticas del cell_manager
        stats = self.cell_manager.get_statistics()
        
        # Configurar texto
        painter.setPen(self.colors["text_info"])
        font = painter.font()
        font.setPointSize(self.styles["text_size_large"])
        painter.setFont(font)
        
        # Construir texto informativo
        info_lines = [
            f"Celdas: {stats['total_cells']}",
            f"Seleccionadas: {stats['selected_cells']}",
            f"Con PTZ: {stats['cells_with_ptz']}",
        ]
        
        if stats['discarded_cells'] > 0:
            info_lines.append(f"Descartadas: {stats['discarded_cells']}")
        
        # Calcular posición según configuración
        info_text = "\n".join(info_lines)
        text_rect = painter.fontMetrics().boundingRect(QRectF(), Qt.TextFlag.TextWordWrap, info_text)
        
        # Fondo semi-transparente
        padding = 8
        bg_rect = QRectF(text_rect.adjusted(-padding, -padding, padding, padding))
        
        # Posicionar según configuración
        if self.info_position == "top_right":
            bg_rect.moveTopRight(QPointF(widget_rect.width() - 10, 10))
        elif self.info_position == "top_left":
            bg_rect.moveTopLeft(QPointF(10, 10))
        elif self.info_position == "bottom_right":
            bg_rect.moveBottomRight(QPointF(widget_rect.width() - 10, widget_rect.height() - 10))
        else:  # bottom_left
            bg_rect.moveBottomLeft(QPointF(10, widget_rect.height() - 10))
        
        # Dibujar fondo
        painter.fillRect(bg_rect, QColor(0, 0, 0, 180))
        
        # Dibujar texto
        text_pos = bg_rect.topLeft() + QPointF(padding, padding + text_rect.height())
        painter.drawText(text_pos, info_text)
    
    def _paint_animations(self, painter: QPainter, widget_rect: QRectF, cell_w: float, cell_h: float):
        """Dibuja efectos de animación"""
        if not self.animated_cells:
            return
        
        current_time = time.time()
        
        for (row, col), animation_data in list(self.animated_cells.items()):
            if current_time - animation_data["start_time"] > animation_data["duration"]:
                # Animación terminada
                del self.animated_cells[(row, col)]
                continue
            
            cell_rect = QRectF(col * cell_w, row * cell_h, cell_w, cell_h)
            self._paint_cell_animation(painter, cell_rect, animation_data, current_time)
    
    def _paint_cell_animation(self, painter: QPainter, cell_rect: QRectF, 
                             animation_data: Dict, current_time: float):
        """Dibuja animación para una celda específica"""
        elapsed = current_time - animation_data["start_time"]
        progress = min(elapsed / animation_data["duration"], 1.0)
        
        animation_type = animation_data["type"]
        
        if animation_type == "pulse":
            # Efecto de pulso
            alpha = int(127 * (1 + 0.5 * (1 - progress)))
            color = QColor(self.colors["animation"])
            color.setAlpha(alpha)
            
            # Crear gradiente radial
            gradient = QRadialGradient(cell_rect.center(), min(cell_rect.width(), cell_rect.height()) / 2)
            gradient.setColorAt(0, color)
            gradient.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
            
            painter.fillRect(cell_rect, QBrush(gradient))
        
        elif animation_type == "highlight":
            # Efecto de highlight
            alpha = int(100 * (1 - progress))
            color = QColor(self.colors["highlight"])
            color.setAlpha(alpha)
            painter.fillRect(cell_rect, color)
    
    # === ANIMACIONES ===
    
    def add_cell_animation(self, row: int, col: int, animation_type: str = "pulse", duration: float = 2.0):
        """Agrega animación a una celda"""
        if not self.styles["animation_enabled"]:
            return
        
        self.animated_cells[(row, col)] = {
            "type": animation_type,
            "start_time": time.time(),
            "duration": duration
        }
    
    def _update_animations(self):
        """Actualiza el frame de animación"""
        self.animation_frame += 1
        if self.animated_cells and self.parent_widget:
            self.parent_widget.update()  # Solicitar repintado
    
    # === UTILIDADES ===
    
    def _invalidate_cache(self):
        """Invalida el cache de rendering"""
        self._grid_lines_cache = None
        self._cache_size = None
        self._cache_grid_size = None
    
    def invalidate_cache(self):
        """Invalida el cache (método público)"""
        self._invalidate_cache()
    
    def get_cell_at_position(self, pos: QPointF, widget_rect: QRectF) -> Optional[Tuple[int, int]]:
        """Obtiene las coordenadas de celda en una posición específica"""
        if not widget_rect.contains(pos):
            return None
        
        cell_w = widget_rect.width() / self.cell_manager.columnas
        cell_h = widget_rect.height() / self.cell_manager.filas
        
        col = int(pos.x() / cell_w)
        row = int(pos.y() / cell_h)
        
        if (0 <= row < self.cell_manager.filas and 
            0 <= col < self.cell_manager.columnas):
            return (row, col)
        
        return None
    
    def get_cell_rect(self, row: int, col: int, widget_rect: QRectF) -> QRectF:
        """Obtiene el rectángulo de una celda específica"""
        cell_w = widget_rect.width() / self.cell_manager.columnas
        cell_h = widget_rect.height() / self.cell_manager.filas
        
        return QRectF(col * cell_w, row * cell_h, cell_w, cell_h)
    
    # === CONFIGURACIÓN PREDEFINIDA ===
    
    def apply_theme(self, theme_name: str):
        """Aplica un tema predefinido"""
        themes = {
            "dark": {
                "selected": QColor(255, 100, 100, 120),
                "discarded": QColor(200, 50, 50, 160),
                "temporal": QColor(100, 255, 100, 120),
                "preset": QColor(100, 100, 255, 100),
                "ptz_mapped": QColor(200, 100, 200, 100),
                "grid_lines": QColor(100, 100, 100, 140),
                "text_preset": QColor(255, 255, 255),
                "text_ptz": QColor(255, 255, 100),
            },
            
            "light": {
                "selected": QColor(255, 0, 0, 80),
                "discarded": QColor(150, 0, 0, 120),
                "temporal": QColor(0, 200, 0, 80),
                "preset": QColor(0, 0, 200, 60),
                "ptz_mapped": QColor(128, 0, 128, 60),
                "grid_lines": QColor(50, 50, 50, 100),
                "text_preset": QColor(255, 255, 255),
                "text_ptz": QColor(200, 200, 0),
            },
            
            "high_contrast": {
                "selected": QColor(255, 0, 0, 200),
                "discarded": QColor(128, 0, 0, 255),
                "temporal": QColor(0, 255, 0, 200),
                "preset": QColor(0, 0, 255, 150),
                "ptz_mapped": QColor(255, 0, 255, 150),
                "grid_lines": QColor(255, 255, 255, 200),
                "text_preset": QColor(255, 255, 255),
                "text_ptz": QColor(255, 255, 0),
            }
        }
        
        theme = themes.get(theme_name)
        if theme:
            for element, color in theme.items():
                self.colors[element] = color
            self._invalidate_cache()
    
    def save_theme(self, theme_name: str) -> Dict[str, Any]:
        """Guarda el tema actual"""
        return {
            "colors": {name: [color.red(), color.green(), color.blue(), color.alpha()] 
                      for name, color in self.colors.items()},
            "styles": self.styles.copy()
        }
    
    def load_theme(self, theme_data: Dict[str, Any]):
        """Carga un tema desde datos"""
        if "colors" in theme_data:
            for name, rgba in theme_data["colors"].items():
                if len(rgba) >= 4:
                    self.colors[name] = QColor(rgba[0], rgba[1], rgba[2], rgba[3])
        
        if "styles" in theme_data:
            self.styles.update(theme_data["styles"])
        
        self._invalidate_cache()