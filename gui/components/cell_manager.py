# gui/components/cell_manager.py
"""
Gestión de estados y operaciones de celdas de la grilla.
Responsabilidades:
- Estados de celdas (seleccionadas, descartadas, temporales)
- Operaciones sobre celdas (seleccionar, descartar, etc.)
- Validación de coordenadas de celdas
- Persistencia de estados
"""

from typing import Set, Tuple, Optional, Dict, Any
from PyQt6.QtCore import QObject, pyqtSignal


class CellManager(QObject):
    """Gestor de estados y operaciones de celdas"""
    
    # Señales para notificar cambios
    cells_changed = pyqtSignal()  # Cuando cambian los estados de celdas
    selection_changed = pyqtSignal(set)  # Cuando cambia la selección
    
    def __init__(self, filas: int, columnas: int, parent=None):
        super().__init__(parent)
        self.filas = filas
        self.columnas = columnas
        
        # Estados de celdas
        self.selected_cells: Set[Tuple[int, int]] = set()
        self.discarded_cells: Set[Tuple[int, int]] = set()
        self.temporal_cells: Set[Tuple[int, int]] = set()
        self.cell_presets: Dict[Tuple[int, int], str] = {}
        self.cell_ptz_map: Dict[Tuple[int, int], Dict[str, Any]] = {}
        
        # Área de detección (compatibilidad con sistema anterior)
        self.area = [0] * (filas * columnas)
    
    def is_valid_cell(self, row: int, col: int) -> bool:
        """Verifica si las coordenadas de celda son válidas"""
        return 0 <= row < self.filas and 0 <= col < self.columnas
    
    def get_cell_index(self, row: int, col: int) -> int:
        """Convierte coordenadas de celda a índice lineal"""
        if not self.is_valid_cell(row, col):
            raise ValueError(f"Coordenadas de celda inválidas: ({row}, {col})")
        return row * self.columnas + col
    
    def get_cell_coords(self, index: int) -> Tuple[int, int]:
        """Convierte índice lineal a coordenadas de celda"""
        if index < 0 or index >= self.filas * self.columnas:
            raise ValueError(f"Índice de celda inválido: {index}")
        row = index // self.columnas
        col = index % self.columnas
        return (row, col)
    
    # === OPERACIONES DE SELECCIÓN ===
    
    def select_cell(self, row: int, col: int) -> bool:
        """Selecciona una celda específica"""
        if not self.is_valid_cell(row, col):
            return False
        
        cell = (row, col)
        if cell not in self.selected_cells:
            self.selected_cells.add(cell)
            self.selection_changed.emit(self.selected_cells.copy())
            self.cells_changed.emit()
            return True
        return False
    
    def deselect_cell(self, row: int, col: int) -> bool:
        """Deselecciona una celda específica"""
        if not self.is_valid_cell(row, col):
            return False
        
        cell = (row, col)
        if cell in self.selected_cells:
            self.selected_cells.remove(cell)
            self.selection_changed.emit(self.selected_cells.copy())
            self.cells_changed.emit()
            return True
        return False
    
    def toggle_cell_selection(self, row: int, col: int) -> bool:
        """Alterna el estado de selección de una celda"""
        if not self.is_valid_cell(row, col):
            return False
        
        cell = (row, col)
        if cell in self.selected_cells:
            return self.deselect_cell(row, col)
        else:
            return self.select_cell(row, col)
    
    def select_multiple_cells(self, cells: Set[Tuple[int, int]]) -> int:
        """Selecciona múltiples celdas. Retorna número de celdas seleccionadas"""
        valid_cells = {cell for cell in cells if self.is_valid_cell(*cell)}
        
        if valid_cells:
            self.selected_cells.update(valid_cells)
            self.selection_changed.emit(self.selected_cells.copy())
            self.cells_changed.emit()
        
        return len(valid_cells)
    
    def clear_selection(self) -> int:
        """Limpia la selección. Retorna número de celdas que estaban seleccionadas"""
        count = len(self.selected_cells)
        if count > 0:
            self.selected_cells.clear()
            self.selection_changed.emit(set())
            self.cells_changed.emit()
        return count
    
    def select_all_cells(self) -> int:
        """Selecciona todas las celdas válidas"""
        all_cells = {(row, col) for row in range(self.filas) for col in range(self.columnas)}
        self.selected_cells = all_cells
        self.selection_changed.emit(self.selected_cells.copy())
        self.cells_changed.emit()
        return len(all_cells)
    
    # === OPERACIONES DE DESCARTE ===
    
    def discard_cell(self, row: int, col: int) -> bool:
        """Marca una celda como descartada (no analizar)"""
        if not self.is_valid_cell(row, col):
            return False
        
        cell = (row, col)
        if cell not in self.discarded_cells:
            self.discarded_cells.add(cell)
            # Remover de selección si estaba seleccionada
            self.selected_cells.discard(cell)
            self.cells_changed.emit()
            return True
        return False
    
    def undiscard_cell(self, row: int, col: int) -> bool:
        """Quita el marcado de descartada de una celda"""
        if not self.is_valid_cell(row, col):
            return False
        
        cell = (row, col)
        if cell in self.discarded_cells:
            self.discarded_cells.remove(cell)
            self.cells_changed.emit()
            return True
        return False
    
    def discard_selected_cells(self) -> int:
        """Descarta todas las celdas seleccionadas"""
        count = len(self.selected_cells)
        if count > 0:
            self.discarded_cells.update(self.selected_cells)
            self.selected_cells.clear()
            self.cells_changed.emit()
        return count
    
    def enable_discarded_cells(self) -> int:
        """Habilita todas las celdas descartadas"""
        count = len(self.discarded_cells)
        if count > 0:
            self.discarded_cells.clear()
            self.cells_changed.emit()
        return count
    
    # === OPERACIONES TEMPORALES ===
    
    def set_temporal_cell(self, row: int, col: int, temporal: bool = True) -> bool:
        """Marca/desmarca una celda como temporal"""
        if not self.is_valid_cell(row, col):
            return False
        
        cell = (row, col)
        changed = False
        
        if temporal and cell not in self.temporal_cells:
            self.temporal_cells.add(cell)
            changed = True
        elif not temporal and cell in self.temporal_cells:
            self.temporal_cells.remove(cell)
            changed = True
        
        if changed:
            self.cells_changed.emit()
        
        return changed
    
    def clear_temporal_cells(self) -> int:
        """Limpia todas las celdas temporales"""
        count = len(self.temporal_cells)
        if count > 0:
            self.temporal_cells.clear()
            self.cells_changed.emit()
        return count
    
    # === PRESETS ===
    
    def set_cell_preset(self, row: int, col: int, preset: str) -> bool:
        """Asigna un preset a una celda"""
        if not self.is_valid_cell(row, col):
            return False
        
        cell = (row, col)
        self.cell_presets[cell] = str(preset)
        self.cells_changed.emit()
        return True
    
    def remove_cell_preset(self, row: int, col: int) -> bool:
        """Remueve el preset de una celda"""
        if not self.is_valid_cell(row, col):
            return False
        
        cell = (row, col)
        if cell in self.cell_presets:
            del self.cell_presets[cell]
            self.cells_changed.emit()
            return True
        return False
    
    def get_cell_preset(self, row: int, col: int) -> Optional[str]:
        """Obtiene el preset de una celda"""
        if not self.is_valid_cell(row, col):
            return None
        return self.cell_presets.get((row, col))
    
    def set_selected_cells_preset(self, preset: str) -> int:
        """Asigna un preset a todas las celdas seleccionadas"""
        count = 0
        for row, col in self.selected_cells:
            if self.set_cell_preset(row, col, preset):
                count += 1
        return count
    
    def clear_selected_cells_preset(self) -> int:
        """Remueve el preset de todas las celdas seleccionadas"""
        count = 0
        for row, col in list(self.selected_cells):
            if self.remove_cell_preset(row, col):
                count += 1
        return count
    
    # === PTZ MAPPING ===
    
    def set_cell_ptz_mapping(self, row: int, col: int, ptz_config: Dict[str, Any]) -> bool:
        """Asigna configuración PTZ a una celda"""
        if not self.is_valid_cell(row, col):
            return False
        
        cell = (row, col)
        self.cell_ptz_map[cell] = ptz_config.copy()
        self.cells_changed.emit()
        return True
    
    def remove_cell_ptz_mapping(self, row: int, col: int) -> bool:
        """Remueve la configuración PTZ de una celda"""
        if not self.is_valid_cell(row, col):
            return False
        
        cell = (row, col)
        if cell in self.cell_ptz_map:
            del self.cell_ptz_map[cell]
            self.cells_changed.emit()
            return True
        return False
    
    def get_cell_ptz_mapping(self, row: int, col: int) -> Optional[Dict[str, Any]]:
        """Obtiene la configuración PTZ de una celda"""
        if not self.is_valid_cell(row, col):
            return None
        return self.cell_ptz_map.get((row, col))
    
    def set_selected_cells_ptz_mapping(self, ptz_config: Dict[str, Any]) -> int:
        """Asigna configuración PTZ a todas las celdas seleccionadas"""
        count = 0
        for row, col in self.selected_cells:
            if self.set_cell_ptz_mapping(row, col, ptz_config):
                count += 1
        return count
    
    def clear_selected_cells_ptz_mapping(self) -> int:
        """Remueve la configuración PTZ de todas las celdas seleccionadas"""
        count = 0
        for row, col in list(self.selected_cells):
            if self.remove_cell_ptz_mapping(row, col):
                count += 1
        return count
    
    # === CONSULTAS DE ESTADO ===
    
    def is_cell_selected(self, row: int, col: int) -> bool:
        """Verifica si una celda está seleccionada"""
        return (row, col) in self.selected_cells
    
    def is_cell_discarded(self, row: int, col: int) -> bool:
        """Verifica si una celda está descartada"""
        return (row, col) in self.discarded_cells
    
    def is_cell_temporal(self, row: int, col: int) -> bool:
        """Verifica si una celda es temporal"""
        return (row, col) in self.temporal_cells
    
    def has_cell_preset(self, row: int, col: int) -> bool:
        """Verifica si una celda tiene preset"""
        return (row, col) in self.cell_presets
    
    def has_cell_ptz_mapping(self, row: int, col: int) -> bool:
        """Verifica si una celda tiene mapping PTZ"""
        return (row, col) in self.cell_ptz_map
    
    def get_cell_state(self, row: int, col: int) -> Dict[str, Any]:
        """Obtiene el estado completo de una celda"""
        if not self.is_valid_cell(row, col):
            return {}
        
        cell = (row, col)
        return {
            "coordinates": (row, col),
            "selected": cell in self.selected_cells,
            "discarded": cell in self.discarded_cells,
            "temporal": cell in self.temporal_cells,
            "preset": self.cell_presets.get(cell),
            "ptz_mapping": self.cell_ptz_map.get(cell),
            "area_state": self.area[self.get_cell_index(row, col)] if self.get_cell_index(row, col) < len(self.area) else 0
        }
    
    # === ESTADÍSTICAS ===
    
    def get_statistics(self) -> Dict[str, int]:
        """Obtiene estadísticas del estado actual"""
        return {
            "total_cells": self.filas * self.columnas,
            "selected_cells": len(self.selected_cells),
            "discarded_cells": len(self.discarded_cells),
            "temporal_cells": len(self.temporal_cells),
            "cells_with_presets": len(self.cell_presets),
            "cells_with_ptz": len(self.cell_ptz_map)
        }
    
    # === OPERACIONES MASIVAS ===
    
    def reset_all_states(self) -> None:
        """Resetea todos los estados de celdas"""
        self.selected_cells.clear()
        self.discarded_cells.clear()
        self.temporal_cells.clear()
        self.cell_presets.clear()
        self.cell_ptz_map.clear()
        self.area = [0] * (self.filas * self.columnas)
        self.cells_changed.emit()
    
    def get_cells_by_state(self, state: str) -> Set[Tuple[int, int]]:
        """Obtiene celdas por estado específico"""
        state_map = {
            "selected": self.selected_cells,
            "discarded": self.discarded_cells,
            "temporal": self.temporal_cells,
            "with_presets": set(self.cell_presets.keys()),
            "with_ptz": set(self.cell_ptz_map.keys())
        }
        return state_map.get(state, set()).copy()
    
    # === COMPATIBILIDAD CON SISTEMA ANTERIOR ===
    
    def set_area_state(self, row: int, col: int, state: int) -> bool:
        """Establece el estado del área (compatibilidad)"""
        if not self.is_valid_cell(row, col):
            return False
        
        index = self.get_cell_index(row, col)
        if index < len(self.area):
            self.area[index] = state
            return True
        return False
    
    def get_area_state(self, row: int, col: int) -> int:
        """Obtiene el estado del área (compatibilidad)"""
        if not self.is_valid_cell(row, col):
            return 0
        
        index = self.get_cell_index(row, col)
        return self.area[index] if index < len(self.area) else 0
    
    # === SERIALIZACIÓN ===
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte el estado a diccionario para serialización"""
        return {
            "filas": self.filas,
            "columnas": self.columnas,
            "selected_cells": list(self.selected_cells),
            "discarded_cells": list(self.discarded_cells),
            "temporal_cells": list(self.temporal_cells),
            "cell_presets": {f"{r},{c}": preset for (r, c), preset in self.cell_presets.items()},
            "cell_ptz_map": {f"{r},{c}": mapping for (r, c), mapping in self.cell_ptz_map.items()},
            "area": self.area
        }
    
    def from_dict(self, data: Dict[str, Any]) -> None:
        """Carga el estado desde un diccionario"""
        self.filas = data.get("filas", self.filas)
        self.columnas = data.get("columnas", self.columnas)
        
        # Convertir listas a sets
        self.selected_cells = set(tuple(cell) for cell in data.get("selected_cells", []))
        self.discarded_cells = set(tuple(cell) for cell in data.get("discarded_cells", []))
        self.temporal_cells = set(tuple(cell) for cell in data.get("temporal_cells", []))
        
        # Convertir presets
        presets_data = data.get("cell_presets", {})
        self.cell_presets = {}
        for key, preset in presets_data.items():
            try:
                r, c = map(int, key.split(","))
                self.cell_presets[(r, c)] = preset
            except (ValueError, AttributeError):
                continue
        
        # Convertir PTZ mappings
        ptz_data = data.get("cell_ptz_map", {})
        self.cell_ptz_map = {}
        for key, mapping in ptz_data.items():
            try:
                r, c = map(int, key.split(","))
                self.cell_ptz_map[(r, c)] = mapping
            except (ValueError, AttributeError):
                continue
        
        # Área
        self.area = data.get("area", [0] * (self.filas * self.columnas))
        
        # Emitir señal de cambio
        self.cells_changed.emit()