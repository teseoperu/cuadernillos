# Cuadernillos PDF

Aplicación de escritorio para preparar PDF en cuadernillos A5 sobre hojas A4 horizontales, con recorte automático y portadilla identificadora.

**Autor:** Thomas Wilber Ramírez Zumaran  
**Contacto:** teseoperu@gmail.com

## Ejecutar desde Python

Instala las dependencias con `uv pip install pymupdf pillow` dentro de un entorno virtual y ejecuta `python cuadernillos.py`.

## Generar el ejecutable de Windows desde GitHub

1. Crea un repositorio en GitHub y sube todos los archivos de este proyecto, incluida la carpeta `.github/workflows/`.
2. Abre la pestaña **Actions** y el flujo **Compilar Cuadernillos PDF para Windows**.
3. Selecciona **Run workflow**.
4. Cuando termine, descarga el artefacto **CuadernillosPDF-Windows** y extrae el `.exe`.
5. Prueba el ejecutable en Windows 10 u 11 antes de compartirlo.

El ejecutable no necesita que los destinatarios instalen Python. Al no estar firmado digitalmente, Windows puede mostrar advertencias de seguridad.

## Impresión

A4 horizontal, doble cara, voltear por borde corto, tamaño real y una página PDF por cara. Verifica primero un cuadernillo de prueba.

## Licencias

Antes de redistribuir, comprueba las licencias de PyMuPDF y de las demás dependencias. PyMuPDF tiene condiciones AGPL/comerciales que pueden afectar la distribución de un ejecutable, incluso gratuito.
