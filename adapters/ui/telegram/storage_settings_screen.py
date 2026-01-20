"""
Storage settings screen for Telegram cache management.
Allows user to configure cache size limits and retention periods.
"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QButtonGroup
)
from qfluentwidgets import (
    CardWidget, ProgressBar, RadioButton, CheckBox,
    PushButton, SubtitleLabel, BodyLabel, CaptionLabel,
    InfoBar, InfoBarPosition, FluentIcon
)

from adapters.telegram.cache_manager import (
    TelegramCacheManager, CacheSizeLimit, CacheRetention, format_size
)


class StorageSettingsScreen(QWidget):
    """Storage configuration screen for Telegram cache."""
    
    # Emitted when settings are changed
    settings_changed = Signal()
    # Emitted when back button is clicked
    back_requested = Signal()
    
    SIZE_OPTIONS = [
        ("2 GB", CacheSizeLimit.GB_2),
        ("4 GB", CacheSizeLimit.GB_4),
        ("6 GB", CacheSizeLimit.GB_6),
        ("8 GB", CacheSizeLimit.GB_8),
        ("10 GB", CacheSizeLimit.GB_10),
        ("30 GB", CacheSizeLimit.GB_30),
        ("50 GB", CacheSizeLimit.GB_50),
    ]
    
    RETENTION_OPTIONS = [
        ("3 días", CacheRetention.DAYS_3),
        ("1 semana", CacheRetention.WEEK_1),
        ("1 mes", CacheRetention.MONTH_1),
        ("Siempre", CacheRetention.UNLIMITED),
    ]
    
    def __init__(self, cache_manager: TelegramCacheManager, parent=None):
        super().__init__(parent)
        self.cache_manager = cache_manager
        self._setup_ui()
        self._load_current_settings()
        self._update_usage_display()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        
        # Header with back button
        header = QHBoxLayout()
        back_btn = PushButton("← Volver")
        back_btn.clicked.connect(self.back_requested.emit)
        header.addWidget(back_btn)
        header.addStretch()
        header.addWidget(SubtitleLabel("📦 Almacenamiento de Telegram"))
        header.addStretch()
        layout.addLayout(header)
        
        # Disk info card
        disk_card = CardWidget()
        disk_layout = QVBoxLayout(disk_card)
        disk_layout.addWidget(BodyLabel("💾 Espacio en disco"))
        self.disk_label = CaptionLabel()
        disk_layout.addWidget(self.disk_label)
        self.disk_bar = ProgressBar()
        disk_layout.addWidget(self.disk_bar)
        layout.addWidget(disk_card)
        
        # Cache usage card
        cache_card = CardWidget()
        cache_layout = QVBoxLayout(cache_card)
        cache_layout.addWidget(BodyLabel("📹 Caché de videos"))
        self.cache_label = CaptionLabel()
        cache_layout.addWidget(self.cache_label)
        self.cache_bar = ProgressBar()
        cache_layout.addWidget(self.cache_bar)
        layout.addWidget(cache_card)
        
        # Size limit card
        size_card = CardWidget()
        size_layout = QVBoxLayout(size_card)
        size_layout.addWidget(BodyLabel("Límite de almacenamiento"))
        
        self.size_group = QButtonGroup(self)
        size_buttons_layout = QHBoxLayout()
        size_buttons_layout.setSpacing(8)
        
        self.size_buttons = {}
        for label, value in self.SIZE_OPTIONS:
            btn = RadioButton(label)
            btn.setProperty('value', value)
            self.size_group.addButton(btn)
            self.size_buttons[value] = btn
            size_buttons_layout.addWidget(btn)
        
        size_layout.addLayout(size_buttons_layout)
        layout.addWidget(size_card)
        
        # Retention card
        retention_card = CardWidget()
        retention_layout = QVBoxLayout(retention_card)
        retention_layout.addWidget(BodyLabel("Conservar archivos por"))
        
        self.retention_group = QButtonGroup(self)
        retention_buttons_layout = QHBoxLayout()
        retention_buttons_layout.setSpacing(8)
        
        self.retention_buttons = {}
        for label, value in self.RETENTION_OPTIONS:
            btn = RadioButton(label)
            btn.setProperty('value', value)
            self.retention_group.addButton(btn)
            self.retention_buttons[value] = btn
            retention_buttons_layout.addWidget(btn)
        
        retention_layout.addLayout(retention_buttons_layout)
        layout.addWidget(retention_card)
        
        # Auto cleanup checkbox
        self.auto_cleanup = CheckBox("Limpieza automática activada")
        self.auto_cleanup.setChecked(True)
        layout.addWidget(self.auto_cleanup)
        
        # Action buttons
        buttons_layout = QHBoxLayout()
        
        clear_btn = PushButton("🗑️ Limpiar ahora")
        clear_btn.clicked.connect(self._on_clear_clicked)
        buttons_layout.addWidget(clear_btn)
        
        save_btn = PushButton("💾 Guardar cambios")
        save_btn.clicked.connect(self._on_save_clicked)
        buttons_layout.addWidget(save_btn)
        
        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)
        
        layout.addStretch()
    
    def _load_current_settings(self):
        """Load current settings into UI."""
        settings = self.cache_manager.settings
        
        # Select current size limit
        if settings.size_limit in self.size_buttons:
            self.size_buttons[settings.size_limit].setChecked(True)
        
        # Select current retention
        if settings.retention_period in self.retention_buttons:
            self.retention_buttons[settings.retention_period].setChecked(True)
        
        # Auto cleanup
        self.auto_cleanup.setChecked(settings.auto_cleanup_enabled)
        
        # Update available limits based on disk space
        self._update_available_limits()
    
    def _update_available_limits(self):
        """Disable size options that exceed available disk space."""
        limits = self.cache_manager.get_available_size_limits()
        
        for label, value, enabled in limits:
            if value in self.size_buttons:
                btn = self.size_buttons[value]
                btn.setEnabled(enabled)
                if not enabled:
                    btn.setText(f"{label} (insuficiente)")
    
    def _update_usage_display(self):
        """Update disk and cache usage displays."""
        # Disk info
        disk_info = self.cache_manager.get_disk_info()
        disk_used_percent = ((disk_info.total - disk_info.free) / disk_info.total * 100) \
            if disk_info.total > 0 else 0
        
        self.disk_bar.setValue(int(disk_used_percent))
        self.disk_label.setText(
            f"{format_size(disk_info.free)} libres de {format_size(disk_info.total)}"
        )
        
        # Cache info
        stats = self.cache_manager.get_cache_stats()
        self.cache_bar.setValue(int(stats['usage_percent']))
        self.cache_label.setText(
            f"{format_size(stats['total_size'])} / {format_size(stats['size_limit'])} "
            f"({stats['file_count']} videos)"
        )
    
    def _on_clear_clicked(self):
        """Handle clear cache button click."""
        freed = self.cache_manager.clear_all()
        self._update_usage_display()
        
        InfoBar.success(
            title="Caché limpiado",
            content=f"Se liberaron {format_size(freed)}",
            position=InfoBarPosition.TOP,
            parent=self.window()
        )
    
    def _on_save_clicked(self):
        """Save settings changes."""
        # Get selected size limit
        for btn in self.size_group.buttons():
            if btn.isChecked():
                self.cache_manager.settings.size_limit = btn.property('value')
                break
        
        # Get selected retention
        for btn in self.retention_group.buttons():
            if btn.isChecked():
                self.cache_manager.settings.retention_period = btn.property('value')
                break
        
        # Auto cleanup
        self.cache_manager.settings.auto_cleanup_enabled = self.auto_cleanup.isChecked()
        
        # Trigger cleanup if needed
        if self.cache_manager.settings.auto_cleanup_enabled:
            self.cache_manager.cleanup()
        
        self._update_usage_display()
        self.settings_changed.emit()
        
        InfoBar.success(
            title="Configuración guardada",
            content="Los cambios se aplicaron correctamente",
            position=InfoBarPosition.TOP,
            parent=self.window()
        )
    
    def refresh(self):
        """Refresh display data."""
        self._update_usage_display()
        self._update_available_limits()
