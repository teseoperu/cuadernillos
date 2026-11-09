#!/usr/bin/env python3
"""Imposición de cuadernillos A5 en A4 apaisado. Requiere PyMuPDF y Pillow."""
import math
import re
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import fitz
from PIL import Image, ImageTk

APP_NOMBRE = 'Cuadernillos PDF'
APP_VERSION = '1.0.0'
APP_AUTOR = 'Thomas Wilber Ramírez Zumaran'
APP_EMAIL = 'teseoperu@gmail.com'

MM = 72 / 25.4
A4_W, A4_H = 297 * MM, 210 * MM
A5_W, A5_H = A4_W / 2, A4_H


def nombre_seguro(texto):
    return re.sub(r'[^\w.-]+', '_', texto.strip(), flags=re.UNICODE).strip('._')[:90] or 'Libro'


def detectar_contenido(pagina, umbral=245):
    """Rectángulo visible aproximado; raster a baja resolución, sin OCR.

    Se detectan píxeles oscuros, no solo texto, para incluir gráficos.
    Si hay un fondo no blanco o marcas al borde, se conserva más área.
    """
    visible = pagina.rect
    if visible.is_empty:
        raise ValueError('Página sin dimensiones válidas')
    factor = min(1.2, 1200 / max(visible.width, visible.height))
    pix = pagina.get_pixmap(matrix=fitz.Matrix(factor, factor), colorspace=fitz.csGRAY, alpha=False)
    w, h = pix.width, pix.height
    data = memoryview(pix.samples)
    xmin, ymin, xmax, ymax = w, h, -1, -1
    # Ignorar puntos aislados: exigir 2 píxeles oscuros por fila/columna.
    cols = [0] * w
    rows = [0] * h
    for y in range(h):
        line = data[y * pix.stride:y * pix.stride + w]
        for x, val in enumerate(line):
            if val < umbral:
                cols[x] += 1
                rows[y] += 1
    xs = [x for x, count in enumerate(cols) if count >= 2]
    ys = [y for y, count in enumerate(rows) if count >= 2]
    if not xs or not ys:
        return visible
    xmin, xmax = xs[0], xs[-1]
    ymin, ymax = ys[0], ys[-1]
    # Coordenadas relativas a la página visual, compatibles con show_pdf_page clip.
    box = fitz.Rect(visible.x0 + xmin / factor, visible.y0 + ymin / factor,
                    visible.x0 + (xmax + 1) / factor, visible.y0 + (ymax + 1) / factor)
    return box & visible


def caja_recorte(pagina, margen_mm=5, activar=True):
    rect = pagina.rect
    if not activar:
        return rect
    contenido = detectar_contenido(pagina)
    margen = margen_mm * MM
    clip = fitz.Rect(contenido.x0 - margen, contenido.y0 - margen,
                     contenido.x1 + margen, contenido.y1 + margen) & rect
    # Protección contra recortes anómalos de documentos con pocos trazos.
    if clip.is_empty or clip.width < rect.width * 0.12 or clip.height < rect.height * 0.12:
        return rect
    return clip


def portada(doc, titulo, autores, numero, total, rango, ancho=A5_W, alto=A5_H):
    p = doc.new_page(width=ancho, height=alto)
    def escribir(texto, rect, size, font='helv', align=1):
        # reduce el tamaño para textos largos, sin desbordar.
        for sz in range(size, 8, -1):
            resultado = p.insert_textbox(rect, texto, fontsize=sz, fontname=font,
                                         align=align, color=(0.1, 0.1, 0.1))
            if resultado >= 0:
                return
        raise ValueError('Texto de portada demasiado largo; acorta el título o los autores.')
    p.draw_rect(fitz.Rect(16*MM, 14*MM, ancho-16*MM, alto-14*MM), color=(.65,.65,.65), width=.6)
    escribir(f'CUADERNILLO {numero:02d} DE {total:02d}', fitz.Rect(20*MM, 25*MM, ancho-20*MM, 44*MM), 13)
    escribir(titulo, fitz.Rect(19*MM, 60*MM, ancho-19*MM, 110*MM), 20)
    escribir(autores or 'Autor no indicado', fitz.Rect(19*MM, 115*MM, ancho-19*MM, 150*MM), 12)
    escribir(f'Páginas originales: {rango[0]}–{rango[1]}', fitz.Rect(18*MM, 169*MM, ancho-18*MM, 183*MM), 11)
    return p


def generar(ruta, destino, titulo, autores, inicio, fin, hojas, modo, recortar=True, margen=5, progreso=None):
    origen = fitz.open(ruta)
    try:
        if origen.needs_pass:
            raise ValueError('El PDF está protegido por contraseña.')
        if not (1 <= inicio <= fin <= len(origen)):
            raise ValueError('Rango de páginas incorrecto.')
        if hojas < 1:
            raise ValueError('La cantidad de hojas debe ser positiva.')
        capacidad = hojas * 4 - 2
        if capacidad < 1:
            raise ValueError('Cada cuadernillo necesita espacio para contenido.')
        segmentos = [(a, min(a + capacidad - 1, fin)) for a in range(inicio, fin + 1, capacidad)]
        total = len(segmentos)
        salida = Path(destino)
        salida.mkdir(parents=True, exist_ok=True)
        prefijo = f'{nombre_seguro(Path(ruta).stem)}_RANGO_{inicio}-{fin}_CUADERNILLOS_{hojas}HOJAS_DOBLAR_A4'
        global_doc = fitz.open() if modo in ('ambos', 'unico') else None
        archivos = []
        recortes = {}
        for n, (a, b) in enumerate(segmentos, 1):
            if progreso:
                progreso(f'Procesando cuadernillo {n}/{total} (págs. {a}–{b})')
            # Cada cuadernillo contiene portada + página 2 vacía + originales + relleno final.
            contenido = fitz.open()
            portada(contenido, titulo, autores, n, total, (a, b))
            contenido.new_page(width=A5_W, height=A5_H)
            for numero in range(a, b + 1):
                fuente = origen[numero - 1]
                if numero not in recortes:
                    recortes[numero] = caja_recorte(fuente, margen, recortar)
                pagina = contenido.new_page(width=A5_W, height=A5_H)
                clip = recortes[numero]
                escala = min(A5_W / clip.width, A5_H / clip.height)
                ancho, alto = clip.width * escala, clip.height * escala
                destino_pagina = fitz.Rect((A5_W - ancho)/2, (A5_H - alto)/2,
                                          (A5_W + ancho)/2, (A5_H + alto)/2)
                pagina.show_pdf_page(destino_pagina, origen, numero-1, clip=clip, keep_proportion=True)
            while len(contenido) % 4:
                contenido.new_page(width=A5_W, height=A5_H)
            impreso = fitz.open()
            N = len(contenido)
            # Cada hoja física corresponde a dos páginas PDF A4: frente y reverso.
            # Frente [última, primera]; reverso [segunda, penúltima].
            for k in range(N // 4):
                pares = [(N - 1 - 2*k, 2*k), (2*k + 1, N - 2 - 2*k)]
                for izq, der in pares:
                    hoja = impreso.new_page(width=A4_W, height=A4_H)
                    hoja.show_pdf_page(fitz.Rect(0, 0, A5_W, A5_H), contenido, izq)
                    hoja.show_pdf_page(fitz.Rect(A5_W, 0, A4_W, A4_H), contenido, der)
            if global_doc is not None:
                global_doc.insert_pdf(impreso)
            if modo in ('ambos', 'separados'):
                archivo = salida / f'{prefijo}_CUADERNILLO_{n:02d}_DE_{total:02d}_PAGS_{a}-{b}.pdf'
                impreso.set_metadata({'title': f'{titulo} - Cuadernillo {n}/{total}', 'author': APP_AUTOR, 'creator': f'{APP_NOMBRE} {APP_VERSION}'})
                impreso.save(str(archivo), garbage=3, deflate=True)
                archivos.append(archivo)
            impreso.close()
            contenido.close()
        if global_doc is not None:
            archivo = salida / f'{prefijo}_COMPLETO.pdf'
            global_doc.set_metadata({'title': f'{titulo} - Cuadernillos para impresión', 'author': APP_AUTOR, 'creator': f'{APP_NOMBRE} {APP_VERSION}'})
            global_doc.save(str(archivo), garbage=3, deflate=True)
            archivos.insert(0, archivo)
            global_doc.close()
        return archivos, segmentos
    finally:
        origen.close()


class Aplicacion(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f'{APP_NOMBRE} v{APP_VERSION} · Imposición A4 → A5')
        self.geometry('850x750')
        self.minsize(720, 620)
        self.ruta = tk.StringVar()
        self.destino = tk.StringVar()
        self.titulo = tk.StringVar()
        self.autores = tk.StringVar()
        self.inicio = tk.StringVar(value='1')
        self.fin = tk.StringVar(value='1')
        self.hojas = tk.StringVar(value='5')
        self.modo = tk.StringVar(value='ambos')
        self.recorte = tk.BooleanVar(value=True)
        self.margen = tk.StringVar(value='5')
        self.estado = tk.StringVar(value='Selecciona un PDF para comenzar.')
        self.imagen = None
        self.crear_menu()
        self.crear_interfaz()

    def crear_menu(self):
        barra = tk.Menu(self)
        ayuda = tk.Menu(barra, tearoff=False)
        ayuda.add_command(label='Acerca de…', command=self.acerca_de)
        barra.add_cascade(label='Ayuda', menu=ayuda)
        self.config(menu=barra)

    def acerca_de(self):
        ventana = tk.Toplevel(self)
        ventana.title('Acerca de Cuadernillos PDF')
        ventana.resizable(False, False)
        ventana.transient(self)
        ventana.grab_set()
        marco = ttk.Frame(ventana, padding=25)
        marco.pack(fill='both', expand=True)
        ttk.Label(marco, text=APP_NOMBRE, font=('Sans', 17, 'bold')).pack(pady=(0, 5))
        ttk.Label(marco, text=f'Versión {APP_VERSION}').pack()
        ttk.Label(marco, text='Herramienta para preparar e imprimir cuadernillos PDF.', wraplength=330, justify='center').pack(pady=(15, 18))
        ttk.Separator(marco, orient='horizontal').pack(fill='x', pady=(0, 15))
        ttk.Label(marco, text='Desarrollado por').pack()
        ttk.Label(marco, text=APP_AUTOR, font=('Sans', 10, 'bold')).pack(pady=(4, 2))
        ttk.Label(marco, text=APP_EMAIL).pack()
        ttk.Label(marco, text=f'© 2026 {APP_AUTOR}', foreground='#666').pack(pady=(16, 12))
        ttk.Button(marco, text='Cerrar', command=ventana.destroy).pack()
        ventana.update_idletasks()
        ventana.geometry(f'+{self.winfo_rootx()+100}+{self.winfo_rooty()+90}')

    def crear_interfaz(self):
        cont = ttk.Frame(self, padding=16)
        cont.pack(fill='both', expand=True)
        cont.columnconfigure(1, weight=1)
        fila = 0
        ttk.Label(cont, text='Preparador de cuadernillos', font=('Sans', 17, 'bold')).grid(row=fila, column=0, columnspan=3, sticky='w', pady=(0, 12))
        fila += 1
        ttk.Label(cont, text='Archivo PDF').grid(row=fila, column=0, sticky='w')
        ttk.Entry(cont, textvariable=self.ruta).grid(row=fila, column=1, sticky='ew', padx=8)
        ttk.Button(cont, text='Examinar…', command=self.elegir).grid(row=fila, column=2)
        fila += 1
        for etiqueta, var in [('Título del libro', self.titulo), ('Autor(es)', self.autores)]:
            ttk.Label(cont, text=etiqueta).grid(row=fila, column=0, sticky='w', pady=4)
            ttk.Entry(cont, textvariable=var).grid(row=fila, column=1, columnspan=2, sticky='ew', padx=(8, 0))
            fila += 1
        opciones = ttk.Frame(cont)
        opciones.grid(row=fila, column=0, columnspan=3, sticky='ew', pady=10)
        for i, (label, var, ancho) in enumerate([('Desde', self.inicio, 7), ('Hasta', self.fin, 7), ('Hojas/cuadernillo', self.hojas, 7)]):
            ttk.Label(opciones, text=label).grid(row=0, column=i*2, padx=(0, 5))
            ttk.Entry(opciones, textvariable=var, width=ancho).grid(row=0, column=i*2+1, padx=(0, 18))
        fila += 1
        ttk.Checkbutton(cont, text='Recorte automático por página', variable=self.recorte).grid(row=fila, column=0, columnspan=2, sticky='w')
        margen_box = ttk.Frame(cont)
        margen_box.grid(row=fila, column=2, sticky='e')
        ttk.Label(margen_box, text='Margen (mm)').pack(side='left', padx=4)
        ttk.Entry(margen_box, textvariable=self.margen, width=5).pack(side='left')
        fila += 1
        modo_box = ttk.LabelFrame(cont, text='Archivos de salida', padding=8)
        modo_box.grid(row=fila, column=0, columnspan=3, sticky='ew', pady=10)
        for i, (nombre, valor) in enumerate([('PDF completo', 'unico'), ('Separados', 'separados'), ('Ambos', 'ambos')]):
            ttk.Radiobutton(modo_box, text=nombre, variable=self.modo, value=valor).grid(row=0, column=i, padx=12)
        fila += 1
        ttk.Label(cont, text='Guardar en').grid(row=fila, column=0, sticky='w')
        ttk.Entry(cont, textvariable=self.destino).grid(row=fila, column=1, sticky='ew', padx=8)
        ttk.Button(cont, text='Carpeta…', command=self.elegir_destino).grid(row=fila, column=2)
        fila += 1
        botones = ttk.Frame(cont)
        botones.grid(row=fila, column=0, columnspan=3, sticky='ew', pady=10)
        ttk.Button(botones, text='Ver distribución', command=self.distribucion).pack(side='left', padx=(0, 8))
        ttk.Button(botones, text='Vista previa del recorte', command=self.previsualizar).pack(side='left', padx=(0, 8))
        self.boton_generar = ttk.Button(botones, text='Generar PDF', command=self.ejecutar)
        self.boton_generar.pack(side='right')
        fila += 1
        ttk.Label(cont, text='Distribución / resultados').grid(row=fila, column=0, columnspan=3, sticky='w')
        fila += 1
        self.salida = tk.Text(cont, height=11, wrap='word', state='disabled')
        self.salida.grid(row=fila, column=0, columnspan=3, sticky='nsew')
        cont.rowconfigure(fila, weight=1)
        fila += 1
        ttk.Label(cont, textvariable=self.estado).grid(row=fila, column=0, columnspan=3, sticky='w', pady=(8, 0))
        fila += 1
        ttk.Label(cont, text='Impresión: A4 horizontal · doble cara · voltear por borde corto · tamaño real · 1 página PDF por cara.',
                  foreground='#555').grid(row=fila, column=0, columnspan=3, sticky='w', pady=(8, 0))
        fila += 1
        ttk.Label(cont, text=f'© 2026 {APP_AUTOR} · {APP_NOMBRE} v{APP_VERSION}', foreground='#777').grid(row=fila, column=0, columnspan=3, sticky='e', pady=(9, 0))

    def mostrar(self, texto):
        self.salida.configure(state='normal')
        self.salida.delete('1.0', 'end')
        self.salida.insert('end', texto)
        self.salida.configure(state='disabled')

    def elegir(self):
        ruta = filedialog.askopenfilename(filetypes=[('PDF', '*.pdf')])
        if not ruta:
            return
        self.ruta.set(ruta)
        self.destino.set(str(Path(ruta).parent))
        try:
            with fitz.open(ruta) as doc:
                if doc.needs_pass:
                    raise ValueError('PDF protegido por contraseña')
                self.fin.set(str(len(doc)))
                metadata = doc.metadata or {}
                self.titulo.set(metadata.get('title') or Path(ruta).stem)
                self.autores.set(metadata.get('author') or '')
                self.estado.set(f'{len(doc)} páginas detectadas.')
        except Exception as e:
            messagebox.showerror('PDF', str(e))

    def elegir_destino(self):
        carpeta = filedialog.askdirectory()
        if carpeta:
            self.destino.set(carpeta)

    def parametros(self):
        ruta = Path(self.ruta.get())
        if not ruta.is_file():
            raise ValueError('Selecciona un PDF existente.')
        a, b, hojas = int(self.inicio.get()), int(self.fin.get()), int(self.hojas.get())
        margen = float(self.margen.get().replace(',', '.'))
        if not 0 <= margen <= 30:
            raise ValueError('El margen debe estar entre 0 y 30 mm.')
        if not 1 <= hojas <= 100:
            raise ValueError('El número de hojas debe estar entre 1 y 100.')
        with fitz.open(str(ruta)) as doc:
            if doc.needs_pass or not 1 <= a <= b <= len(doc):
                raise ValueError('Rango incorrecto o PDF protegido.')
        if not self.titulo.get().strip():
            raise ValueError('Escribe el título del libro.')
        if not Path(self.destino.get()).is_dir():
            raise ValueError('Selecciona una carpeta de salida válida.')
        return a, b, hojas, margen

    def distribucion(self):
        try:
            a, b, hojas, _ = self.parametros()
            capacidad = hojas * 4 - 2
            partes = [(i, min(i+capacidad-1, b)) for i in range(a, b+1, capacidad)]
            lineas = [f'Total: {len(partes)} cuadernillos. Capacidad: {capacidad} páginas originales por cuadernillo.\n']
            for n, (x, y) in enumerate(partes, 1):
                paginas = 2 + y - x + 1
                hojas_usadas = math.ceil(paginas/4)
                blancos = hojas_usadas*4-paginas
                lineas.append(f'{n:02d}/{len(partes):02d} · Originales {x}–{y} · {hojas_usadas} hojas · {blancos} blancas finales')
            self.mostrar('\n'.join(lineas))
        except Exception as e:
            messagebox.showerror('Datos', str(e))

    def previsualizar(self):
        try:
            a, _, _, margen = self.parametros()
            with fitz.open(self.ruta.get()) as doc:
                p = doc[a-1]
                clip = caja_recorte(p, margen, self.recorte.get())
                pix = p.get_pixmap(matrix=fitz.Matrix(1.1, 1.1), colorspace=fitz.csRGB, alpha=False)
                imagen = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                from PIL import ImageDraw
                dibujo = ImageDraw.Draw(imagen)
                base = p.rect
                escala_x, escala_y = pix.width/base.width, pix.height/base.height
                dibujo.rectangle(((clip.x0-base.x0)*escala_x, (clip.y0-base.y0)*escala_y,
                                   (clip.x1-base.x0)*escala_x, (clip.y1-base.y0)*escala_y), outline='red', width=3)
                imagen.thumbnail((620, 680))
            ventana = tk.Toplevel(self)
            ventana.title(f'Recorte propuesto · página original {a}')
            foto = ImageTk.PhotoImage(imagen)
            etiqueta = ttk.Label(ventana, image=foto)
            etiqueta.image = foto
            etiqueta.pack(padx=12, pady=12)
            ttk.Label(ventana, text='El rectángulo rojo indica el contenido que se conservará. Revisa también páginas especiales.').pack(pady=(0, 10))
        except Exception as e:
            messagebox.showerror('Vista previa', str(e))

    def ejecutar(self):
        try:
            a, b, hojas, margen = self.parametros()
        except Exception as e:
            messagebox.showerror('Datos', str(e))
            return
        self.boton_generar.configure(state='disabled')
        self.estado.set('Generando archivos…')
        args = (self.ruta.get(), self.destino.get(), self.titulo.get().strip(),
                self.autores.get().strip(), a, b, hojas, self.modo.get(), self.recorte.get(), margen)
        def progreso(s):
            self.after(0, lambda: self.estado.set(s))
        def trabajo():
            try:
                archivos, partes = generar(*args, progreso=progreso)
                self.after(0, lambda: self.finalizado(archivos, partes))
            except Exception as e:
                self.after(0, lambda error=str(e): self.fallo(error))
        threading.Thread(target=trabajo, daemon=True).start()

    def finalizado(self, archivos, partes):
        self.boton_generar.configure(state='normal')
        self.estado.set(f'Listo: {len(partes)} cuadernillos, {len(archivos)} PDF generados.')
        self.mostrar('\n'.join(str(a) for a in archivos))
        messagebox.showinfo('Proceso completado', f'Se generaron {len(archivos)} archivos PDF en:\n{self.destino.get()}')

    def fallo(self, error):
        self.boton_generar.configure(state='normal')
        self.estado.set('No se pudo completar el proceso.')
        messagebox.showerror('Error', error)


if __name__ == '__main__':
    Aplicacion().mainloop()
