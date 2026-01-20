"""
Telegram login screen with QR Code authentication flow.
Uses persistent TelegramAsyncWorker for Telegram operations.
"""
from io import BytesIO
import qrcode
from PIL import Image

from PySide6.QtCore import Signal, QTimer, Qt
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QLabel
)
from qfluentwidgets import (
    PushButton, SubtitleLabel, BodyLabel, CaptionLabel,
    PasswordLineEdit, InfoBar, InfoBarPosition,
    ProgressRing, CardWidget
)

from adapters.telegram.async_worker import get_telegram_worker, TelegramOp
from adapters.telegram.tdlib_client import AuthState


class TelegramLoginScreen(QWidget):
    """QR Code Telegram login screen."""
    
    # Emitted when login is successful
    login_successful = Signal()
    # Emitted when user wants to go back
    back_requested = Signal()
    
    def __init__(self, tdlib_client, parent=None):
        super().__init__(parent)
        self.tdlib_client = tdlib_client
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        
        # Header with back button
        header = QHBoxLayout()
        self.back_btn = PushButton("← Volver")
        self.back_btn.clicked.connect(self.back_requested.emit)
        header.addWidget(self.back_btn)
        header.addStretch()
        self.title_label = SubtitleLabel("✈️ Telegram")
        header.addWidget(self.title_label)
        header.addStretch()
        layout.addLayout(header)
        
        # Stacked widget for different steps
        self.stack = QStackedWidget()
        
        # Step 1: QR Code
        self.qr_page = self._create_qr_page()
        self.stack.addWidget(self.qr_page)
        
        # Step 2: 2FA Password
        self.password_page = self._create_password_page()
        self.stack.addWidget(self.password_page)
        
        # Step 3: Loading
        self.loading_page = self._create_loading_page()
        self.stack.addWidget(self.loading_page)
        
        layout.addWidget(self.stack)
        layout.addStretch()
    
    def _create_qr_page(self) -> QWidget:
        """Create QR code display page."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(20)
        
        layout.addStretch()
        
        card = CardWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setAlignment(Qt.AlignCenter)
        
        card_layout.addWidget(SubtitleLabel("Inicia sesión con Telegram"))
        
        # Instructions
        instructions = BodyLabel(
            "1. Abre Telegram en tu celular\n"
            "2. Ve a Ajustes > Dispositivos > Vincular un dispositivo\n"
            "3. Escanea este código QR"
        )
        instructions.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(instructions)
        
        # QR Image Placeholder
        self.qr_label = QLabel()
        self.qr_label.setFixedSize(250, 250)
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setStyleSheet("background-color: white; border-radius: 10px;")
        card_layout.addWidget(self.qr_label)
        
        # Refresh button (if expired)
        self.refresh_btn = PushButton("Actualizar código")
        self.refresh_btn.clicked.connect(self.check_auth)
        self.refresh_btn.hide()
        card_layout.addWidget(self.refresh_btn)
        
        layout.addWidget(card)
        layout.addStretch()
        
        return page
    
    def _create_password_page(self) -> QWidget:
        """Create 2FA password input page."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(20)
        
        layout.addStretch()
        
        card = CardWidget()
        card_layout = QVBoxLayout(card)
        
        card_layout.addWidget(SubtitleLabel("🔐 Verificación de dos pasos"))
        card_layout.addWidget(CaptionLabel(
            "Tu cuenta tiene habilitada la verificación en dos pasos"
        ))
        
        self.password_input = PasswordLineEdit()
        self.password_input.setPlaceholderText("Contraseña")
        self.password_input.returnPressed.connect(self._on_password_submitted)
        card_layout.addWidget(self.password_input)
        
        self.password_btn = PushButton("Verificar →")
        self.password_btn.clicked.connect(self._on_password_submitted)
        card_layout.addWidget(self.password_btn)
        
        layout.addWidget(card)
        layout.addStretch()
        
        return page
    
    def _create_loading_page(self) -> QWidget:
        """Create loading spinner page."""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        layout.addStretch()
        
        spinner_layout = QHBoxLayout()
        spinner_layout.addStretch()
        self.spinner = ProgressRing()
        spinner_layout.addWidget(self.spinner)
        spinner_layout.addStretch()
        layout.addLayout(spinner_layout)
        
        self.loading_label = BodyLabel("Conectando...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.loading_label)
        
        layout.addStretch()
        
        return page
    
    def check_auth(self):
        """Start the QR login/check process."""
        self.stack.setCurrentWidget(self.loading_page)
        self.loading_label.setText("Conectando...")
        self.refresh_btn.hide()
        
        worker = get_telegram_worker()
        worker.execute(
            TelegramOp.GET_QR_CODE,
            self._on_qr_url_received
        )
    
    def _on_qr_url_received(self, success: bool, result):
        """Handle QR URL receipt."""
        if success:
            if result == "AUTHORIZED":
                self.login_successful.emit()
                return

            self._generate_qr_image(result)
            self.stack.setCurrentWidget(self.qr_page)
            
            # Start waiting for scan
            worker = get_telegram_worker()
            worker.execute(
                TelegramOp.WAIT_FOR_QR_SCAN,
                self._on_scan_result
            )
        else:
            self._show_error(f"Error al generar QR: {result}")
            self.refresh_btn.show()
            self.stack.setCurrentWidget(self.qr_page)

    def _generate_qr_image(self, url: str):
        """Generate QR image from URL and display it."""
        try:
            qr = qrcode.QRCode(box_size=10, border=1)
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert PIL image to QPixmap
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            qimg = QImage.fromData(buffer.getvalue())
            pixmap = QPixmap.fromImage(qimg)
            
            self.qr_label.setPixmap(pixmap.scaled(
                250, 250, Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
        except Exception as e:
            self._show_error(f"Error visualizando QR: {e}")

    def _on_scan_result(self, success: bool, result):
        """Handle QR scan result."""
        if success:
            if result == AuthState.READY:
                self.login_successful.emit()
            elif result == AuthState.WAIT_PASSWORD:
                self.stack.setCurrentWidget(self.password_page)
                self.password_input.setFocus()
        else:
            # Check if it was a timeout or stop
            if "timeout" in str(result).lower():
                 self._show_error("El código QR expiró.")
                 self.refresh_btn.show()
            else:
                self._show_error(f"Error de conexión: {result}")
                self.refresh_btn.show()
    
    def _on_password_submitted(self):
        """Handle 2FA password submission."""
        password = self.password_input.text()
        
        if not password:
            self._show_error("Ingresa tu contraseña")
            return
        
        self._show_loading("Verificando contraseña...")
        
        worker = get_telegram_worker()
        worker.execute(
            TelegramOp.SEND_PASSWORD,
            self._on_password_result,
            password=password
        )
    
    def _on_password_result(self, success: bool, result):
        """Handle password submission result."""
        if success:
            self.login_successful.emit()
        else:
            self._show_error(f"Contraseña incorrecta: {result}")
            self.stack.setCurrentWidget(self.password_page)
            self.password_input.clear()
            self.password_input.setFocus()
    
    def _show_loading(self, message: str):
        """Show loading spinner with message."""
        self.loading_label.setText(message)
        self.stack.setCurrentWidget(self.loading_page)
        
    def _show_error(self, message: str):
        """Show error notification."""
        InfoBar.error(
            title="Error",
            content=message,
            position=InfoBarPosition.TOP,
            parent=self.window()
        )
    
    def reset(self):
        """Reset login form to initial state."""
        self.password_input.clear()
        self.check_auth()
