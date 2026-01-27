#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Click Overlay + Control Panel (PySide6)

Avec :
- Boucle de séquence (checkbox Loop)
- Taille individuelle des cercles (par point)
- Randomisation du clic dans le cercle (checkbox Random)
- Hotkey ESC pour stopper
- Explorateur de fichiers pour Save/Load
- Correction DPI : pyautogui clique pile sur les cercles
"""

import json
import os
import sys
import time
import random
import keyboard
from dataclasses import dataclass
from typing import List

from PySide6 import QtCore, QtGui, QtWidgets

# pyautogui pour cliquer
try:
    import pyautogui
    HAS_PYAUTO = True
    pyautogui.PAUSE = 0.02
    pyautogui.FAILSAFE = True
except Exception:
    HAS_PYAUTO = False


@dataclass
class ClickPoint:
    x: int
    y: int
    press_ms: int = 100
    wait_ms: int = 200
    radius: int = 18


class PointsController(QtCore.QObject):
    changed = QtCore.Signal()
    selection_changed = QtCore.Signal(int)

    def __init__(self):
        super().__init__()
        self.points: List[ClickPoint] = []
        self.selected: int = -1
        self.loop = False
        self.random_clicks = False
        self._stop = False  # flag d’arrêt
        # ratios de correction DPI (définis dans main)
        self.scale_x = 1.0
        self.scale_y = 1.0

    def stop(self):
        """Arrêt demandé (via ESC ou bouton)"""
        self._stop = True

    def select(self, idx: int):
        if idx < -1 or idx >= len(self.points):
            idx = -1
        self.selected = idx
        self.selection_changed.emit(self.selected)
        self.changed.emit()

    def add_point(self, p: ClickPoint, select=True, at_index=None):
        if at_index is None:
            self.points.append(p)
            idx = len(self.points) - 1
        else:
            at_index = max(0, min(at_index, len(self.points)))
            self.points.insert(at_index, p)
            idx = at_index
        if select:
            self.select(idx)
        else:
            self.changed.emit()

    def delete_selected(self):
        if 0 <= self.selected < len(self.points):
            del self.points[self.selected]
            if self.selected >= len(self.points):
                self.selected = len(self.points) - 1
            self.selection_changed.emit(self.selected)
            self.changed.emit()

    def move_selected(self, delta: QtCore.QPoint, overlay_widget: QtWidgets.QWidget):
        if 0 <= self.selected < len(self.points):
            p = self.points[self.selected]
            local = overlay_widget.mapFromGlobal(QtCore.QPoint(p.x, p.y))
            local += delta
            r = overlay_widget.rect().adjusted(6, 6, -6, -6)
            local.setX(max(r.left(), min(r.right(), local.x())))
            local.setY(max(r.top(), min(r.bottom(), local.y())))
            g = overlay_widget.mapToGlobal(local)
            p.x, p.y = int(g.x()), int(g.y())
            self.changed.emit()

    def reorder_selected(self, direction: int):
        i = self.selected
        if 0 <= i < len(self.points):
            j = i + direction
            if 0 <= j < len(self.points):
                self.points[i], self.points[j] = self.points[j], self.points[i]
                self.select(j)

    def clear(self):
        self.points.clear()
        self.select(-1)

    def save_txt(self, path="sequence.txt"):
        with open(path, "w", encoding="utf-8") as f:
            f.write("# index x y press_ms wait_ms radius\n")
            for i, p in enumerate(self.points, 1):
                f.write(f"{i} {p.x} {p.y} {p.press_ms} {p.wait_ms} {p.radius}\n")

    def load_txt(self, path="sequence.txt"):
        pts = []
        if not os.path.exists(path):
            return False
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                parts = s.split()
                if len(parts) < 5:
                    continue
                x = int(parts[1]); y = int(parts[2])
                press_ms = int(parts[3]); wait_ms = int(parts[4])
                radius = int(parts[5]) if len(parts) >= 6 else 18
                pts.append(ClickPoint(x, y, press_ms, wait_ms, radius))
        self.points = pts
        self.select(0 if self.points else -1)
        self.changed.emit()
        return True

    def play(self, hide_widgets: List[QtWidgets.QWidget]):
        if not HAS_PYAUTO:
            return "pyautogui indisponible (pip install pyautogui)."
        if not self.points:
            return "Aucun point."
        self._stop = False

        # hotkey ESC pour arrêter
        keyboard.add_hotkey("esc", lambda: self.stop())

        for w in hide_widgets:
            w.hide()
        time.sleep(0.4)
        try:
            for t in (3, 2, 1):
                print(f"Départ dans {t}…")
                time.sleep(1)

            while True:
                for p in self.points:
                    if self._stop:
                        raise InterruptedError("Arrêt demandé (ESC ou Stop)")

                    if self.random_clicks:
                        dx = random.randint(-p.radius, p.radius)
                        dy = random.randint(-p.radius, p.radius)
                        px, py = p.x + dx, p.y + dy
                    else:
                        px, py = p.x, p.y

                    # Correction DPI
                    px = int(px * self.scale_x)
                    py = int(py * self.scale_y)

                    pyautogui.moveTo(px, py)
                    pyautogui.mouseDown()
                    time.sleep(max(0.0, p.press_ms / 1000))
                    pyautogui.mouseUp()
                    time.sleep(max(0.0, p.wait_ms / 1000))

                if not self.loop:
                    break
        except InterruptedError:
            msg = "Séquence stoppée."
        except pyautogui.FailSafeException:
            msg = "Interrompu (coin haut-gauche FAILSAFE)."
        except Exception as e:
            msg = f"Erreur: {e}"
        else:
            msg = "Séquence terminée."
        finally:
            keyboard.unhook_all_hotkeys()  # clean
            for w in hide_widgets:
                w.show()
        return msg


class OverlayWindow(QtWidgets.QWidget):
    pointPicked = QtCore.Signal(int)

    def __init__(self, controller: PointsController, screen: QtGui.QScreen):
        super().__init__(None)
        self.ctrl = controller
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setWindowFlag(QtCore.Qt.FramelessWindowHint, True)
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)

        self.setGeometry(screen.geometry())
        self.dragging = False
        self.last_mouse_pos = QtCore.QPoint()

        self.ctrl.changed.connect(self.update)
        self.ctrl.selection_changed.connect(lambda _: self.update())

        self.show()

    def paintEvent(self, e: QtGui.QPaintEvent):
        p = QtGui.QPainter(self)
        p.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.TextAntialiasing)

        if len(self.ctrl.points) >= 2:
            pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 90), 2)
            p.setPen(pen)
            for i in range(len(self.ctrl.points) - 1):
                a = self._local_of(self.ctrl.points[i])
                b = self._local_of(self.ctrl.points[i+1])
                p.drawLine(a, b)

        for i, pt in enumerate(self.ctrl.points):
            loc = self._local_of(pt)
            selected = (i == self.ctrl.selected)
            fill = QtGui.QColor(0, 180, 255, 230) if not selected else QtGui.QColor(255, 210, 0, 230)
            pen = QtGui.QPen(QtGui.QColor(20, 20, 20, 230), 2)
            p.setPen(pen); p.setBrush(fill)
            p.drawEllipse(loc, pt.radius, pt.radius)
            p.setPen(QtGui.QColor(0, 0, 0))
            font = p.font(); font.setBold(True); p.setFont(font)
            txt = str(i+1)
            rect = QtCore.QRectF(loc.x()-pt.radius, loc.y()-pt.radius, pt.radius*2, pt.radius*2)
            p.drawText(rect, QtCore.Qt.AlignCenter, txt)

    def _local_of(self, pt: ClickPoint) -> QtCore.QPoint:
        return self.mapFromGlobal(QtCore.QPoint(pt.x, pt.y))

    def _hit_index(self, pos_local: QtCore.QPoint) -> int:
        for i in reversed(range(len(self.ctrl.points))):
            loc = self._local_of(self.ctrl.points[i])
            if (loc - pos_local).manhattanLength() <= self.ctrl.points[i].radius + 4:
                return i
        return -1

    def mousePressEvent(self, e: QtGui.QMouseEvent):
        if e.button() == QtCore.Qt.LeftButton:
            idx = self._hit_index(e.position().toPoint())
            if idx != -1:
                self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
                self.ctrl.select(idx)
                self.dragging = True
                self.last_mouse_pos = e.globalPos()
                self.pointPicked.emit(idx)
            else:
                self.ctrl.select(-1)

    def mouseMoveEvent(self, e: QtGui.QMouseEvent):
        if self.dragging and 0 <= self.ctrl.selected < len(self.ctrl.points):
            cur = e.globalPosition().toPoint()
            delta_local = self.mapFromGlobal(cur) - self.mapFromGlobal(self.last_mouse_pos)
            self.ctrl.move_selected(delta_local, self)
            self.last_mouse_pos = cur

    def mouseReleaseEvent(self, e: QtGui.QMouseEvent):
        if e.button() == QtCore.Qt.LeftButton:
            self.dragging = False
            self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)


class ControlWindow(QtWidgets.QWidget):
    def __init__(self, controller: PointsController, overlay: OverlayWindow):
        super().__init__()
        self.ctrl = controller
        self.overlay = overlay
        self.setWindowTitle("Click Sequencer – Contrôle")
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        self.setMinimumWidth(420)

        main = QtWidgets.QVBoxLayout(self)

        top = QtWidgets.QHBoxLayout()
        self.btn_add = QtWidgets.QPushButton("+")
        self.btn_del = QtWidgets.QPushButton("−")
        self.btn_up = QtWidgets.QPushButton("Up")
        self.btn_down = QtWidgets.QPushButton("Down")
        top.addWidget(self.btn_add); top.addWidget(self.btn_del)
        top.addWidget(self.btn_up); top.addWidget(self.btn_down)
        main.addLayout(top)

        self.list = QtWidgets.QListWidget()
        self.list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        main.addWidget(self.list, 1)

        form = QtWidgets.QFormLayout()
        self.spin_press = QtWidgets.QSpinBox(); self.spin_press.setRange(0, 600000); self.spin_press.setSuffix(" ms")
        self.spin_wait = QtWidgets.QSpinBox(); self.spin_wait.setRange(0, 600000); self.spin_wait.setSuffix(" ms")
        self.spin_radius = QtWidgets.QSpinBox(); self.spin_radius.setRange(5, 200); self.spin_radius.setSuffix(" px")
        form.addRow("Temps d’appui:", self.spin_press)
        form.addRow("Attente après:", self.spin_wait)
        form.addRow("Taille cercle:", self.spin_radius)
        main.addLayout(form)

        options = QtWidgets.QHBoxLayout()
        self.chk_loop = QtWidgets.QCheckBox("Loop")
        self.chk_random = QtWidgets.QCheckBox("Random clicks")
        options.addWidget(self.chk_loop)
        options.addWidget(self.chk_random)
        main.addLayout(options)

        actions = QtWidgets.QHBoxLayout()
        self.btn_save = QtWidgets.QPushButton("Save")
        self.btn_load = QtWidgets.QPushButton("Load")
        self.btn_play = QtWidgets.QPushButton("Play")
        self.btn_clear = QtWidgets.QPushButton("Clear")
        actions.addWidget(self.btn_save); actions.addWidget(self.btn_load)
        actions.addWidget(self.btn_play); actions.addWidget(self.btn_clear)
        main.addLayout(actions)

        self.status = QtWidgets.QLabel("")
        self.status.setStyleSheet("color:#0f0;")
        main.addWidget(self.status)

        self.btn_add.clicked.connect(self._on_add)
        self.btn_del.clicked.connect(self.ctrl.delete_selected)
        self.btn_up.clicked.connect(lambda: self.ctrl.reorder_selected(-1))
        self.btn_down.clicked.connect(lambda: self.ctrl.reorder_selected(+1))
        self.btn_save.clicked.connect(self._on_save)
        self.btn_load.clicked.connect(self._on_load)
        self.btn_play.clicked.connect(self._on_play)
        self.btn_clear.clicked.connect(self.ctrl.clear)

        self.list.currentRowChanged.connect(self.ctrl.select)
        self.ctrl.selection_changed.connect(self._sync_form_from_selection)
        self.ctrl.changed.connect(self._refresh_list)

        self.spin_press.valueChanged.connect(self._apply_spin_changes)
        self.spin_wait.valueChanged.connect(self._apply_spin_changes)
        self.spin_radius.valueChanged.connect(self._apply_spin_changes)

        self.chk_loop.stateChanged.connect(lambda s: setattr(self.ctrl, "loop", bool(s)))
        self.chk_random.stateChanged.connect(lambda s: setattr(self.ctrl, "random_clicks", bool(s)))

        self.overlay.pointPicked.connect(self.list.setCurrentRow)

        self._refresh_list()
        self._sync_form_from_selection(self.ctrl.selected)

        self.show()

    def _on_add(self):
        rect = self.overlay.rect()
        center_local = rect.center()
        center_global = self.overlay.mapToGlobal(center_local)
        self.ctrl.add_point(ClickPoint(center_global.x(), center_global.y()), select=True)

    def _on_save(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Sauvegarder séquence", "", "Text Files (*.txt)")
        if path:
            self.ctrl.save_txt(path)
            self._ok(f"Sauvé → {path}")

    def _on_load(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Charger séquence", "", "Text Files (*.txt)")
        if path:
            ok = self.ctrl.load_txt(path)
            if ok: self._ok(f"Chargé {path}")
            else: self._warn("Fichier invalide")

    def _on_play(self):
        msg = self.ctrl.play([self.overlay, self])
        if msg.startswith("Erreur") or "indisponible" in msg:
            self._err(msg)
        else:
            self._ok(msg)

    def _apply_spin_changes(self):
        i = self.ctrl.selected
        if 0 <= i < len(self.ctrl.points):
            self.ctrl.points[i].press_ms = int(self.spin_press.value())
            self.ctrl.points[i].wait_ms = int(self.spin_wait.value())
            self.ctrl.points[i].radius = int(self.spin_radius.value())
            self.ctrl.changed.emit()

    def _refresh_list(self):
        self.list.blockSignals(True)
        self.list.clear()
        for i, p in enumerate(self.ctrl.points, 1):
            self.list.addItem(f"{i:02d} ({p.x},{p.y}) press={p.press_ms}ms wait={p.wait_ms}ms r={p.radius}px")
        if 0 <= self.ctrl.selected < self.list.count():
            self.list.setCurrentRow(self.ctrl.selected)
        self.list.blockSignals(False)

    def _sync_form_from_selection(self, idx: int):
        has = (0 <= idx < len(self.ctrl.points))
        self.spin_press.setEnabled(has)
        self.spin_wait.setEnabled(has)
        self.spin_radius.setEnabled(has)
        self.btn_del.setEnabled(has)
        self.btn_up.setEnabled(has)
        self.btn_down.setEnabled(has)
        if has:
            p = self.ctrl.points[idx]
            self.spin_press.blockSignals(True)
            self.spin_wait.blockSignals(True)
            self.spin_radius.blockSignals(True)
            self.spin_press.setValue(p.press_ms)
            self.spin_wait.setValue(p.wait_ms)
            self.spin_radius.setValue(p.radius)
            self.spin_press.blockSignals(False)
            self.spin_wait.blockSignals(False)
            self.spin_radius.blockSignals(False)

    def _ok(self, txt): self._status(txt, "#0f0")
    def _warn(self, txt): self._status(txt, "#fa0")
    def _err(self, txt): self._status(txt, "#f55")
    def _status(self, txt, color):
        self.status.setText(txt)
        self.status.setStyleSheet(f"color:{color};")


def main():
    import ctypes
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

    app = QtWidgets.QApplication(sys.argv)

    screen = QtGui.QGuiApplication.primaryScreen()
    geo = screen.geometry()

    # calcul ratio DPI
    pg_w, pg_h = pyautogui.size()
    scale_x = pg_w / geo.width()
    scale_y = pg_h / geo.height()

    ctrl = PointsController()
    ctrl.scale_x = scale_x
    ctrl.scale_y = scale_y

    overlay = OverlayWindow(ctrl, screen)
    panel = ControlWindow(ctrl, overlay)

    geo = screen.availableGeometry()
    panel.move(geo.left() + 40, geo.top() + 40)

    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
