# Guía de Instalación para Linux (Kubuntu/Ubuntu)

Esta aplicación está desarrollada en Python y utiliza Qt6 (PySide6). Aunque el desarrollo original fue en Windows, es totalmente compatible con Linux siguiendo estos pasos.

## 1. Instalar dependencias del sistema

A diferencia de Windows, donde incluimos los binarios de VLC y MPV, en Linux es mucho mejor usar los que vienen en los repositorios oficiales.

Abre una terminal y ejecuta:

```bash
sudo apt update
sudo apt install python3-venv python3-pip vlc libvlc-dev libmpv-dev
```

*   `python3-venv`: Para crear entornos virtuales.
*   `vlc` y `libvlc-dev`: Reproductor VLC y sus cabeceras para que Python pueda usarlo.
*   `libmpv-dev`: Librería necesaria para que `python-mpv` funcione.

## 2. Crear y regenerar el Entorno Virtual

Es recomendable aislar las librerías de Python del proyecto.

1.  Navega a la carpeta del proyecto:
    ```bash
    cd /ruta/a/shadow_player
    ```

2.  Crea el entorno virtual (hazlo solo la primera vez o si quieres regenerarlo):
    ```bash
    # Si existe una carpeta .venv antigua, bórrala primero
    rm -rf .venv

    # Crear nuevo entorno llamado .venv
    python3 -m venv .venv
    ```

3.  Activa el entorno virtual:
    ```bash
    source .venv/bin/activate
    ```
    *(Verás que tu prompt cambia indicando `(.venv)`)*

## 3. Instalar librerías de Python

Con el entorno activado, instala lo necesario:

```bash
pip install -r requirements.txt
```

**Nota sobre `PySide6-Fluent-Widgets`:** Si tienes problemas de compatibilidad en Linux con la versión específica de PySide6, intenta actualizar pip primero: `pip install --upgrade pip`.

## 4. Ejecutar la aplicación

Simplemente corre:

```bash
python main.py
```

## Notas adicionales

*   **Rendimiento de Video:** Si usas QtPlayer (Backend por defecto de QtMultimedia), asegúrate de tener instalados los codecs de GStreamer:
    ```bash
    sudo apt install gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav
    ```
*   **Problemas de Wayland:** Si usas Wayland y la ventana se ve extraña, puedes forzar el uso de X11 con:
    ```bash
    QT_QPA_PLATFORM=xcb python main.py
    ```
