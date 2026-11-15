"""PyQt5 / PyQt6 compatibility for Rocky 9 (Qt5) and Rocky 10 (Qt6)."""

from __future__ import annotations

QT_VERSION = 0

try:
    from PyQt5.QtCore import (  # type: ignore
        QT_VERSION_STR,
        QDir,
        QEvent,
        QFileInfo,
        QMimeData,
        QModelIndex,
        QObject,
        QPoint,
        QSettings,
        QSize,
        QSortFilterProxyModel,
        Qt,
        QThread,
        QTimer,
        QUrl,
        pyqtSignal,
    )
    from PyQt5.QtGui import (  # type: ignore
        QDesktopServices,
        QDrag,
        QFont,
        QIcon,
        QKeySequence,
        QPainter,
        QPalette,
        QPixmap,
        QStandardItem,
        QStandardItemModel,
    )
    from PyQt5.QtWidgets import (  # type: ignore
        QAbstractItemView,
        QAction,
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFileDialog,
        QFileIconProvider,
        QFormLayout,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QInputDialog,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMenu,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QSizePolicy,
        QSpinBox,
        QSplitter,
        QStatusBar,
        QStyle,
        QStyledItemDelegate,
        QScrollArea,
        QTextBrowser,
        QTableView,
        QTableWidget,
        QTableWidgetItem,
        QToolBar,
        QToolButton,
        QTreeWidget,
        QTreeWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    QT_VERSION = 5

    def exec_dialog(dialog):
        return dialog.exec_()

    def exec_menu(menu, pos):
        return menu.exec_(pos)

    def enum_val(group, name):
        return getattr(group, name)

except ImportError:  # pragma: no cover - Rocky 10 / Qt6
    from PyQt6.QtCore import (  # type: ignore
        QT_VERSION_STR,
        QDir,
        QEvent,
        QFileInfo,
        QMimeData,
        QModelIndex,
        QObject,
        QPoint,
        QSettings,
        QSize,
        QSortFilterProxyModel,
        Qt,
        QThread,
        QTimer,
        QUrl,
        pyqtSignal,
    )
    from PyQt6.QtGui import (  # type: ignore
        QAction,
        QDesktopServices,
        QDrag,
        QFont,
        QIcon,
        QKeySequence,
        QPainter,
        QPalette,
        QPixmap,
        QStandardItem,
        QStandardItemModel,
    )
    from PyQt6.QtWidgets import (  # type: ignore
        QAbstractItemView,
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFileDialog,
        QFileIconProvider,
        QFormLayout,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QInputDialog,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMenu,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QSizePolicy,
        QSpinBox,
        QSplitter,
        QStatusBar,
        QStyle,
        QStyledItemDelegate,
        QScrollArea,
        QTextBrowser,
        QTableView,
        QTableWidget,
        QTableWidgetItem,
        QToolBar,
        QToolButton,
        QTreeWidget,
        QTreeWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    QT_VERSION = 6

    def exec_dialog(dialog):
        return dialog.exec()

    def exec_menu(menu, pos):
        return menu.exec(pos)

    def enum_val(group, name):
        member = getattr(group, name, None)
        if member is not None:
            return member
        # Qt6 nested enums: Qt.AlignmentFlag.AlignLeft
        for attr in dir(group):
            nested = getattr(group, attr)
            if hasattr(nested, name):
                return getattr(nested, name)
        raise AttributeError(name)


def qt_align(name: str):
    if QT_VERSION == 5:
        return getattr(Qt, name)
    return getattr(Qt.AlignmentFlag, name)


def qt_item_flag(name: str):
    if QT_VERSION == 5:
        return getattr(Qt, name)
    return getattr(Qt.ItemFlag, name)


def qt_item_data(name: str):
    if QT_VERSION == 5:
        return getattr(Qt, name)
    return getattr(Qt.ItemDataRole, name)


def qt_key(name: str):
    if QT_VERSION == 5:
        return getattr(Qt, name)
    return getattr(Qt.Key, name)


def qt_sort(name: str):
    if QT_VERSION == 5:
        return getattr(Qt, name)
    return getattr(Qt.SortOrder, name)


def qt_orient(name: str):
    if QT_VERSION == 5:
        return getattr(Qt, name)
    return getattr(Qt.Orientation, name)


def qt_drop(name: str):
    if QT_VERSION == 5:
        return getattr(Qt, name)
    return getattr(Qt.DropAction, name)


def qt_select_mode(name: str):
    if QT_VERSION == 5:
        return getattr(QAbstractItemView, name)
    return getattr(QAbstractItemView.SelectionMode, name)


def qt_select_behavior(name: str):
    if QT_VERSION == 5:
        return getattr(QAbstractItemView, name)
    return getattr(QAbstractItemView.SelectionBehavior, name)


def qt_edit_trigger(name: str):
    if QT_VERSION == 5:
        return getattr(QAbstractItemView, name)
    return getattr(QAbstractItemView.EditTrigger, name)


def qt_drag_drop(name: str):
    if QT_VERSION == 5:
        return getattr(QAbstractItemView, name)
    return getattr(QAbstractItemView.DragDropMode, name)


def qt_header_resize(name: str):
    if QT_VERSION == 5:
        return getattr(QHeaderView, name)
    return getattr(QHeaderView.ResizeMode, name)


def qt_style_pixmap(name: str):
    if QT_VERSION == 5:
        return getattr(QStyle, name)
    return getattr(QStyle.StandardPixmap, name)


def qt_shortcut_context(name: str):
    if QT_VERSION == 5:
        return getattr(Qt, name)
    return getattr(Qt.ShortcutContext, name)


def qt_focus(name: str):
    if QT_VERSION == 5:
        return getattr(Qt, name)
    return getattr(Qt.FocusPolicy, name)


def qt_toolbutton(name: str):
    if QT_VERSION == 5:
        return getattr(QToolButton, name)
    return getattr(QToolButton.ToolButtonStyle, name) if hasattr(QToolButton, "ToolButtonStyle") else getattr(QToolButton, name)


def qt_window_mod(name: str):
    if QT_VERSION == 5:
        return getattr(Qt, name)
    return getattr(Qt.WindowModality, name)


def qt_case(name: str):
    if QT_VERSION == 5:
        return getattr(Qt, name)
    return getattr(Qt.CaseSensitivity, name)


def qt_match(name: str):
    if QT_VERSION == 5:
        return getattr(Qt, name)
    return getattr(Qt.MatchFlag, name)


def qt_echo(name: str):
    if QT_VERSION == 5:
        return getattr(QLineEdit, name)
    return getattr(QLineEdit.EchoMode, name)


def qt_dialog_role(name: str):
    if QT_VERSION == 5:
        return getattr(QDialogButtonBox, name)
    return getattr(QDialogButtonBox.ButtonRole, name)


def qt_dialog_std(name: str):
    if QT_VERSION == 5:
        return getattr(QDialogButtonBox, name)
    return getattr(QDialogButtonBox.StandardButton, name)


def qt_msg_btn(name: str):
    if QT_VERSION == 5:
        return getattr(QMessageBox, name)
    return getattr(QMessageBox.StandardButton, name)


def qt_msg_icon(name: str):
    if QT_VERSION == 5:
        return getattr(QMessageBox, name)
    return getattr(QMessageBox.Icon, name)


def qt_frame_shape(name: str):
    if QT_VERSION == 5:
        return getattr(QFrame, name)
    return getattr(QFrame.Shape, name)
