#!/usr/bin/env python3
import json
import sqlite3
import time
import sys
import os
import logging
import threading
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from tkinter.font import Font

# Configuraciones originales
BAUD_RATE = 9600
HEALTHCHECK_JSON = {"healtcheck": 1}
HEALTHCHECK_TIMEOUT = 2.5
SERIAL_OPEN_RESET_WAIT = 2.0
HEALTHCHECK_ATTEMPTS = 3
HEALTHCHECK_INTERVAL = 0.15
DB_FILE = "alumnos.db"
DEBUG = False

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('rfid_system.log'),
        logging.StreamHandler(sys.stdout) if DEBUG else logging.NullHandler()
    ]
)

# Importar librerías seriales
try:
    import serial
    import serial.tools.list_ports as list_ports
except ImportError as e:
    messagebox.showerror("Error", "La librería pyserial no está instalada.\nEjecuta: pip install pyserial")
    sys.exit(1)

class RFIDSystem:
    def __init__(self, root):
        self.root = root
        self.root.title("Sistema de Gestión RFID")
        self.root.geometry("800x600")
        self.root.configure(bg='#f0f0f0')
        
        # Variables
        self.puerto = None
        self.reading_card = False
        self.serial_connection = None  # Conexión serial persistente
        self.connection_lock = threading.Lock()  # Lock para thread-safety
        
        # Configurar evento de cierre de ventana
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Configurar base de datos
        self.setup_database()
        
        # Configurar fuentes
        self.font_title = Font(family="Arial", size=16, weight="bold")
        self.font_normal = Font(family="Arial", size=10)
        self.font_button = Font(family="Arial", size=11, weight="bold")
        
        # Crear GUI
        self.create_widgets()
        
        # Buscar Arduino al iniciar
        self.buscar_arduino()
    
    def setup_database(self):
        """Configura la base de datos"""
        try:
            self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
            self.cursor = self.conn.cursor()
            self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS alumnos (
                uid TEXT PRIMARY KEY,
                nombre TEXT NOT NULL,
                grupo TEXT NOT NULL,
                control TEXT NOT NULL
            )
            """)
            self.conn.commit()
            logging.info("Base de datos inicializada correctamente")
        except sqlite3.Error as e:
            messagebox.showerror("Error Crítico", f"Error al inicializar la base de datos: {e}")
            sys.exit(1)
    
    def create_widgets(self):
        """Crear widgets de la interfaz mejorada"""
        # Crear notebook para pestañas
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Pestaña Principal
        self.create_main_tab()
        
        # Pestaña de Administración
        self.create_admin_tab()
        
        # Pestaña de Reportes
        self.create_reports_tab()
        
        # Barra de estado
        self.create_status_bar()
        
        # Deshabilitar botones inicialmente
        self.toggle_buttons(False)
    
    def create_main_tab(self):
        """Crear la pestaña principal"""
        main_tab = ttk.Frame(self.notebook)
        self.notebook.add(main_tab, text="Principal")
        
        # Frame principal con scroll
        canvas = tk.Canvas(main_tab, bg='#f0f0f0')
        scrollbar = ttk.Scrollbar(main_tab, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Título principal
        header_frame = tk.Frame(scrollable_frame, bg='#2c3e50', height=80)
        header_frame.pack(fill=tk.X, padx=20, pady=(20, 0))
        header_frame.pack_propagate(False)
        title_label = tk.Label(header_frame, text="SISTEMA DE GESTIÓN RFID", 
                              font=Font(family="Arial", size=18, weight="bold"), 
                              bg='#2c3e50', fg='white')
        title_label.pack(expand=True)
        
        subtitle = tk.Label(header_frame, text="Control de Acceso y Administración de Alumnos", 
                           font=Font(family="Arial", size=10), 
                           bg='#2c3e50', fg='#bdc3c7')
        subtitle.pack()
        
        # Estado de conexión mejorado
        self.status_frame = tk.LabelFrame(scrollable_frame, text="Estado del Sistema", 
                                         font=self.font_normal, bg='#f0f0f0', padx=15, pady=10)
        self.status_frame.pack(fill=tk.X, padx=20, pady=20)
        
        status_inner = tk.Frame(self.status_frame, bg='#f0f0f0')
        status_inner.pack(fill=tk.X)
        
        self.status_label = tk.Label(status_inner, text="Buscando lector RFID...", 
                                   font=Font(family="Arial", size=11, weight="bold"), 
                                   bg='#f0f0f0', fg='#f39c12')
        self.status_label.pack(side=tk.LEFT)
        
        self.connection_indicator = tk.Label(status_inner, text="●", 
                                           font=Font(size=16), 
                                           bg='#f0f0f0', fg='#e74c3c')
        self.connection_indicator.pack(side=tk.RIGHT)
        
        # Grid de botones mejorado
        buttons_container = tk.Frame(scrollable_frame, bg='#f0f0f0')
        buttons_container.pack(fill=tk.X, padx=30, pady=20)
        
        # Primera fila de botones
        row1_frame = tk.Frame(buttons_container, bg='#f0f0f0')
        row1_frame.pack(fill=tk.X, pady=8)
        self.btn_registrar = self.create_modern_button(row1_frame, "Registrar\nNuevo Alumno", 
                                                     '#3498db', self.abrir_registro)
        self.btn_registrar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        self.btn_consultar = self.create_modern_button(row1_frame, "Consulta\nAutomática", 
                                                     '#27ae60', self.abrir_consulta)
        self.btn_consultar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))
        
        # Segunda fila de botones
        row2_frame = tk.Frame(buttons_container, bg='#f0f0f0')
        row2_frame.pack(fill=tk.X, pady=8)
        
        self.btn_eliminar = self.create_modern_button(row2_frame, "Eliminar\nTarjeta", 
                                                    '#e74c3c', self.abrir_eliminacion)
        self.btn_eliminar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        self.btn_estadisticas = self.create_modern_button(row2_frame, "Ver\nEstadísticas", 
                                                        '#9b59b6', self.mostrar_estadisticas)
        self.btn_estadisticas.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))
        
        # Tercera fila - botones adicionales
        row3_frame = tk.Frame(buttons_container, bg='#f0f0f0')
        row3_frame.pack(fill=tk.X, pady=8)
        
        self.btn_lista_alumnos = self.create_modern_button(row3_frame, "Lista de\nAlumnos", 
                                                         '#34495e', self.mostrar_lista_alumnos)
        self.btn_lista_alumnos.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        self.btn_backup = self.create_modern_button(row3_frame, "Backup\nDatos", 
                                                  '#16a085', self.crear_backup)
        self.btn_backup.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))
        
        # Log mejorado
        log_frame = tk.LabelFrame(scrollable_frame, text="Registro de Actividad", 
                                font=self.font_normal, bg='#f0f0f0', padx=10, pady=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Frame para controles del log
        log_controls = tk.Frame(log_frame, bg='#f0f0f0')
        log_controls.pack(fill=tk.X, pady=(0, 10))
        tk.Button(log_controls, text="Limpiar", command=self.limpiar_log,
                 bg='#95a5a6', fg='white', font=Font(size=9)).pack(side=tk.RIGHT, padx=5)
        
        tk.Button(log_controls, text="Guardar", command=self.guardar_log,
                 bg='#3498db', fg='white', font=Font(size=9)).pack(side=tk.RIGHT, padx=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, width=80, 
                                                font=("Consolas", 9), bg='#2c3e50', 
                                                fg='#ecf0f1', insertbackground='white')
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Configurar el canvas
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def create_modern_button(self, parent, text, color, command):
        """Crear botón moderno con efectos hover"""
        btn = tk.Button(parent, text=text, bg=color, fg='white', 
                       font=Font(family="Arial", size=11, weight="bold"),
                       command=command, relief='flat', bd=0, 
                       pady=18, padx=20, cursor='hand2',
                       width=12, height=3)
        
        # Efectos hover
        def on_enter(e):
            btn.config(bg=self.darken_color(color))
        
        def on_leave(e):
            btn.config(bg=color)
        
        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        
        return btn
    
    def darken_color(self, color):
        """Oscurecer un color para efecto hover"""
        color_map = {
            '#3498db': '#2980b9',
            '#27ae60': '#229954',
            '#e74c3c': '#c0392b',
            '#9b59b6': '#8e44ad',
            '#34495e': '#2c3e50',
            '#16a085': '#138d75',
            '#f39c12': '#e67e22'
        }
        return color_map.get(color, color)
    
    def create_admin_tab(self):
        """Crear la pestaña de administración"""
        admin_tab = ttk.Frame(self.notebook)
        self.notebook.add(admin_tab, text="Administración")
        
        # Frame principal
        admin_frame = ttk.Frame(admin_tab, padding="20")
        admin_frame.pack(fill=tk.BOTH, expand=True)
        
        # Título
        title = tk.Label(admin_frame, text="Panel de Administración", 
                        font=Font(family="Arial", size=16, weight="bold"), 
                        bg='#f0f0f0', fg='#2c3e50')
        title.pack(pady=(0, 20))
        
        # Grid de funciones administrativas
        admin_grid = tk.Frame(admin_frame, bg='#f0f0f0')
        admin_grid.pack(fill=tk.BOTH, expand=True)
        
        # Gestión de datos
        data_frame = tk.LabelFrame(admin_grid, text="Gestión de Datos", 
                                 font=self.font_normal, padx=15, pady=10)
        data_frame.pack(fill=tk.X, pady=10)
        
        btn_frame1 = tk.Frame(data_frame)
        btn_frame1.pack(fill=tk.X, pady=5)
        self.create_admin_button(btn_frame1, "Exportar Excel", '#27ae60', self.exportar_excel).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.create_admin_button(btn_frame1, "Importar Datos", '#3498db', self.importar_datos).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        btn_frame2 = tk.Frame(data_frame)
        btn_frame2.pack(fill=tk.X, pady=5)
        
        self.create_admin_button(btn_frame2, "Sincronizar", '#9b59b6', self.sincronizar_datos).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.create_admin_button(btn_frame2, "Limpiar BD", '#e74c3c', self.limpiar_bd).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Configuración del sistema
        config_frame = tk.LabelFrame(admin_grid, text="Configuración", 
                                   font=self.font_normal, padx=15, pady=10)
        config_frame.pack(fill=tk.X, pady=10)
        
        btn_frame3 = tk.Frame(config_frame)
        btn_frame3.pack(fill=tk.X, pady=5)
        
        self.create_admin_button(btn_frame3, "Configuración", '#34495e', self.abrir_configuracion).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.create_admin_button(btn_frame3, "Reconectar", '#f39c12', self.reconectar_arduino).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
    
    def create_reports_tab(self):
        """Crear la pestaña de reportes"""
        reports_tab = ttk.Frame(self.notebook)
        self.notebook.add(reports_tab, text="Reportes")
        
        # Frame principal
        reports_frame = ttk.Frame(reports_tab, padding="20")
        reports_frame.pack(fill=tk.BOTH, expand=True)
        
        # Título
        title = tk.Label(reports_frame, text="Centro de Reportes", 
                        font=Font(family="Arial", size=16, weight="bold"), 
                        bg='#f0f0f0', fg='#2c3e50')
        title.pack(pady=(0, 20))
        
        # Estadísticas rápidas
        stats_frame = tk.LabelFrame(reports_frame, text="Estadísticas Rápidas", 
                                  font=self.font_normal, padx=15, pady=10)
        stats_frame.pack(fill=tk.X, pady=10)
        
        self.stats_container = tk.Frame(stats_frame, bg='#f0f0f0')
        self.stats_container.pack(fill=tk.X)
        
        self.update_quick_stats()
        
        # Gráficos y reportes
        charts_frame = tk.LabelFrame(reports_frame, text="Reportes Avanzados", 
                                   font=self.font_normal, padx=15, pady=10)
        charts_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        btn_frame4 = tk.Frame(charts_frame)
        btn_frame4.pack(fill=tk.X, pady=10)
        self.create_admin_button(btn_frame4, "Gráfico por Grupos", '#3498db', self.grafico_grupos).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.create_admin_button(btn_frame4, "Reporte Completo", '#27ae60', self.reporte_completo).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
    
    def create_status_bar(self):
        """Crear barra de estado"""
        self.status_bar = tk.Frame(self.root, bg='#34495e', height=25)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.status_text = tk.Label(self.status_bar, text="Sistema iniciado", 
                                   bg='#34495e', fg='white', 
                                   font=Font(family="Arial", size=9))
        self.status_text.pack(side=tk.LEFT, padx=10)
        
        # Reloj
        self.clock_label = tk.Label(self.status_bar, bg='#34495e', fg='white', 
                                   font=Font(family="Arial", size=9))
        self.clock_label.pack(side=tk.RIGHT, padx=10)
        
        self.update_clock()
    
    def create_admin_button(self, parent, text, color, command):
        """Crear botón para panel de administración"""
        return tk.Button(parent, text=text, bg=color, fg='white', 
                        font=Font(family="Arial", size=10, weight="bold"),
                        command=command, relief='flat', bd=0, 
                        pady=10, cursor='hand2')
    
    def log_message(self, message, level="INFO"):
        """Agregar mensaje al log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        color_map = {
            "INFO": "black",
            "SUCCESS": "green",
            "ERROR": "red",
            "WARNING": "orange"
        }
        
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        
        # Limitar líneas del log
        lines = int(self.log_text.index('end-1c').split('.')[0])
        if lines > 100:
            self.log_text.delete(1.0, "2.0")
    
    def limpiar_log(self):
        """Limpiar el log de actividad"""
        self.log_text.delete(1.0, tk.END)
        self.log_message("Log limpiado", "INFO")
    
    def guardar_log(self):
        """Guardar el log en un archivo"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"log_sistema_{timestamp}.txt"
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(self.log_text.get(1.0, tk.END))
            
            messagebox.showinfo("Éxito", f"Log guardado en {filename}")
            self.log_message(f"Log guardado en {filename}", "SUCCESS")
        except Exception as e:
            messagebox.showerror("Error", f"Error al guardar log: {e}")
    
    def update_clock(self):
        """Actualizar reloj en barra de estado"""
        current_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.clock_label.config(text=current_time)
        self.root.after(1000, self.update_clock)
    
    def update_quick_stats(self):
        """Actualizar estadísticas rápidas"""
        try:
            # Limpiar contenedor anterior
            for widget in self.stats_container.winfo_children():
                widget.destroy()
            
            # Obtener estadísticas
            self.cursor.execute("SELECT COUNT(*) FROM alumnos")
            total = self.cursor.fetchone()[0]
            
            self.cursor.execute("SELECT COUNT(DISTINCT grupo) FROM alumnos")
            grupos = self.cursor.fetchone()[0]
              # Crear widgets de estadísticas
            stats_data = [
                ("Total Alumnos", total, "#3498db"),
                ("Grupos", grupos, "#27ae60"),
                ("BD Conectada", "OK", "#16a085")
            ]
            
            for i, (label, value, color) in enumerate(stats_data):
                frame = tk.Frame(self.stats_container, bg=color, padx=10, pady=8)
                frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
                
                tk.Label(frame, text=str(value), bg=color, fg='white', 
                        font=Font(size=16, weight="bold")).pack()
                tk.Label(frame, text=label, bg=color, fg='white', 
                        font=Font(size=9)).pack()
                
        except Exception as e:
            print(f"Error actualizando estadísticas: {e}")
    
    def mostrar_lista_alumnos(self):
        """Mostrar lista completa de alumnos"""
        try:
            self.cursor.execute("SELECT uid, nombre, grupo, control FROM alumnos ORDER BY nombre")
            alumnos = self.cursor.fetchall()
            
            # Crear ventana
            lista_window = tk.Toplevel(self.root)
            lista_window.title("Lista de Alumnos Registrados")
            lista_window.geometry("800x500")
            lista_window.configure(bg='#f0f0f0')
            
            lista_window.transient(self.root)
            lista_window.grab_set()
            
            # Frame principal
            main_frame = ttk.Frame(lista_window, padding="20")
            main_frame.pack(fill=tk.BOTH, expand=True)
              # Título
            title = tk.Label(main_frame, text="Lista de Alumnos Registrados", 
                           font=Font(size=16, weight="bold"), bg='#f0f0f0')
            title.pack(pady=(0, 20))
            
            # Treeview para mostrar datos
            columns = ("UID", "Nombre", "Grupo", "Control")
            tree = ttk.Treeview(main_frame, columns=columns, show="headings", height=15)
            
            # Configurar columnas
            tree.heading("UID", text="UID")
            tree.heading("Nombre", text="Nombre")
            tree.heading("Grupo", text="Grupo")
            tree.heading("Control", text="N° Control")
            
            tree.column("UID", width=100)
            tree.column("Nombre", width=200)
            tree.column("Grupo", width=100)
            tree.column("Control", width=100)
            
            # Añadir datos
            for alumno in alumnos:
                tree.insert("", tk.END, values=alumno)
            
            # Scrollbar
            scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)
            
            tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # Botones
            btn_frame = tk.Frame(main_frame, bg='#f0f0f0')
            btn_frame.pack(fill=tk.X, pady=10)
            
            tk.Button(btn_frame, text="Cerrar", command=lista_window.destroy,
                     bg='#95a5a6', fg='white', font=self.font_button).pack(side=tk.RIGHT)
            
            self.log_message(f"Lista de alumnos mostrada ({len(alumnos)} registros)", "INFO")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al mostrar lista: {e}")
    
    def crear_backup(self):
        """Crear backup de la base de datos"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = f"backup_alumnos_{timestamp}.db"
            
            # Copiar base de datos
            import shutil
            shutil.copy2(DB_FILE, backup_file)
            
            messagebox.showinfo("Éxito", f"Backup creado exitosamente:\n{backup_file}")
            self.log_message(f"Backup creado: {backup_file}", "SUCCESS")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al crear backup: {e}")
    
    def exportar_excel(self):
        """Exportar datos a Excel (simulado con CSV)"""
        try:
            import csv
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"alumnos_export_{timestamp}.csv"
            
            self.cursor.execute("SELECT uid, nombre, grupo, control FROM alumnos ORDER BY nombre")
            alumnos = self.cursor.fetchall()
            
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['UID', 'Nombre', 'Grupo', 'Número Control'])
                writer.writerows(alumnos)
            
            messagebox.showinfo("Éxito", f"Datos exportados a {filename}")
            self.log_message(f"Datos exportados a {filename}", "SUCCESS")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al exportar: {e}")
    
    def importar_datos(self):
        """Importar datos desde archivo CSV"""
        from tkinter import filedialog
        try:
            filename = filedialog.askopenfilename(
                title="Seleccionar archivo CSV",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
            )
            
            if not filename:
                return
            
            import csv
            count = 0
            errors = 0
            
            with open(filename, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    try:
                        self.cursor.execute(
                            "INSERT OR REPLACE INTO alumnos (uid, nombre, grupo, control) VALUES (?, ?, ?, ?)",
                            (row['UID'], row['Nombre'], row['Grupo'], row['Número Control'])
                        )
                        count += 1
                    except Exception as e:
                        errors += 1
                        print(f"Error en fila: {e}")
            
            self.conn.commit()
            messagebox.showinfo("Éxito", f"Importación completada:\n{count} registros importados\n{errors} errores")
            self.log_message(f"Datos importados: {count} registros, {errors} errores", "SUCCESS")
            self.update_quick_stats()
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al importar: {e}")
    
    def sincronizar_datos(self):
        """Sincronizar y validar integridad de datos"""
        try:
            # Verificar integridad
            self.cursor.execute("SELECT COUNT(*) FROM alumnos WHERE uid IS NULL OR nombre IS NULL")
            invalid_records = self.cursor.fetchone()[0]
            
            if invalid_records > 0:
                messagebox.showwarning("Advertencia", f"Se encontraron {invalid_records} registros con datos faltantes")
            
            # Actualizar estadísticas
            self.update_quick_stats()
            
            messagebox.showinfo("Éxito", "Sincronización completada")
            self.log_message("Datos sincronizados correctamente", "SUCCESS")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error en sincronización: {e}")
    
    def limpiar_bd(self):
        """Limpiar toda la base de datos"""
        respuesta = messagebox.askyesnocancel(
            "Confirmar Limpieza",
            "⚠️ ATENCIÓN: Esta acción eliminará TODOS los registros de alumnos.\n\n"
            "¿Desea crear un backup antes de continuar?\n\n"
            "• Sí: Crear backup y limpiar\n"
            "• No: Limpiar sin backup\n"
            "• Cancelar: No hacer nada"
        )
        
        if respuesta is None:  # Cancelar
            return
        elif respuesta:  # Sí - crear backup
            self.crear_backup()
        
        # Confirmar limpieza
        final_confirm = messagebox.askyesno(
            "Confirmación Final",
            "¿Está completamente seguro de eliminar todos los registros?",
            icon='warning'
        )
        
        if final_confirm:
            try:
                self.cursor.execute("DELETE FROM alumnos")
                self.conn.commit()
                
                messagebox.showinfo("Éxito", "Base de datos limpiada exitosamente")
                self.log_message("Base de datos limpiada completamente", "WARNING")
                self.update_quick_stats()
                
            except Exception as e:
                messagebox.showerror("Error", f"Error al limpiar BD: {e}")
    
    def abrir_configuracion(self):
        """Abrir ventana de configuración"""
        config_window = tk.Toplevel(self.root)
        config_window.title("Configuración del Sistema")
        config_window.geometry("500x400")
        config_window.configure(bg='#f0f0f0')
        
        config_window.transient(self.root)
        config_window.grab_set()
        
        frame = ttk.Frame(config_window, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
        title = tk.Label(frame, text="Configuración del Sistema", 
                        font=Font(size=16, weight="bold"), bg='#f0f0f0')
        title.pack(pady=(0, 20))
        
        # Configuraciones (ejemplo)
        tk.Label(frame, text="Puerto Serial:", font=self.font_normal, bg='#f0f0f0').pack(anchor=tk.W, pady=5)
        puerto_var = tk.StringVar(value=self.puerto or "No conectado")
        tk.Entry(frame, textvariable=puerto_var, state='readonly', font=self.font_normal).pack(fill=tk.X, pady=5)
        
        tk.Label(frame, text="Timeout de lectura (segundos):", font=self.font_normal, bg='#f0f0f0').pack(anchor=tk.W, pady=5)
        timeout_var = tk.StringVar(value="10")
        tk.Entry(frame, textvariable=timeout_var, font=self.font_normal).pack(fill=tk.X, pady=5)
        
        tk.Button(frame, text="Cerrar", command=config_window.destroy,
                 bg='#95a5a6', fg='white', font=self.font_button).pack(pady=20)

    def reconectar_arduino(self):
        """Reconectar con el Arduino"""
        def reconectar():
            self.root.after(0, lambda: self.status_label.config(text="Reconectando...", fg='#f39c12'))
            self.root.after(0, lambda: self.toggle_buttons(False))
            
            # Cerrar conexión actual
            self.cerrar_conexion_serial()
            
            # Buscar de nuevo
            self.buscar_arduino()
        
        threading.Thread(target=reconectar, daemon=True).start()
    
    def grafico_grupos(self):
        """Mostrar gráfico de distribución por grupos"""
        try:
            self.cursor.execute("SELECT grupo, COUNT(*) FROM alumnos GROUP BY grupo ORDER BY grupo")
            datos = self.cursor.fetchall()
            
            if not datos:
                messagebox.showinfo("Sin datos", "No hay datos para mostrar")
                return
            
            # Crear ventana simple para mostrar datos
            graph_window = tk.Toplevel(self.root)
            graph_window.title("Distribución por Grupos")
            graph_window.geometry("600x400")
            graph_window.configure(bg='#f0f0f0')
            
            graph_window.transient(self.root)
            graph_window.grab_set()
            
            frame = ttk.Frame(graph_window, padding="20")
            frame.pack(fill=tk.BOTH, expand=True)
            title = tk.Label(frame, text="Distribución de Alumnos por Grupo", 
                           font=Font(size=14, weight="bold"), bg='#f0f0f0')
            title.pack(pady=(0, 20))
                      # Mostrar datos en formato texto (simulando gráfico)
            for grupo, cantidad in datos:
                grupo_frame = tk.Frame(frame, bg='#f0f0f0')
                grupo_frame.pack(fill=tk.X, pady=5)
                
                tk.Label(grupo_frame, text=f"{grupo}:", font=self.font_normal, bg='#f0f0f0').pack(side=tk.LEFT)
                
                # Barra visual simple
                bar_width = min(cantidad * 10, 200)
                bar_frame = tk.Frame(grupo_frame, bg='#3498db', height=20, width=bar_width)
                bar_frame.pack(side=tk.LEFT, padx=10)
                bar_frame.pack_propagate(False)
                
                tk.Label(grupo_frame, text=f"{cantidad} estudiantes", font=self.font_normal, bg='#f0f0f0').pack(side=tk.LEFT)
            
            tk.Button(frame, text="Cerrar", command=graph_window.destroy,
                     bg='#95a5a6', fg='white', font=self.font_button).pack(pady=20)
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al generar gráfico: {e}")
    
    def reporte_completo(self):
        """Generar reporte completo del sistema"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"reporte_completo_{timestamp}.txt"
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("="*50 + "\n")
                f.write("REPORTE COMPLETO DEL SISTEMA RFID\n")
                f.write("="*50 + "\n\n")
                f.write(f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n")
                
                # Estadísticas generales
                self.cursor.execute("SELECT COUNT(*) FROM alumnos")
                total = self.cursor.fetchone()[0]
                f.write(f"Total de alumnos registrados: {total}\n\n")
                
                # Por grupos
                f.write("DISTRIBUCIÓN POR GRUPOS:\n")
                f.write("-" * 25 + "\n")
                self.cursor.execute("SELECT grupo, COUNT(*) FROM alumnos GROUP BY grupo ORDER BY grupo")
                for grupo, cantidad in self.cursor.fetchall():
                    f.write(f"{grupo}: {cantidad} estudiantes\n")
                
                f.write("\n" + "="*50 + "\n")
                f.write("LISTADO COMPLETO DE ALUMNOS\n")
                f.write("="*50 + "\n\n")
                
                self.cursor.execute("SELECT nombre, grupo, control, uid FROM alumnos ORDER BY grupo, nombre")
                for nombre, grupo, control, uid in self.cursor.fetchall():
                    f.write(f"Nombre: {nombre}\n")
                    f.write(f"Grupo: {grupo}\n")
                    f.write(f"Control: {control}\n")
                    f.write(f"UID: {uid}\n")
                    f.write("-" * 30 + "\n")
            
            messagebox.showinfo("Éxito", f"Reporte completo generado:\n{filename}")
            self.log_message(f"Reporte completo generado: {filename}", "SUCCESS")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al generar reporte: {e}")
    
    def toggle_buttons(self, enabled):
        """Habilitar/deshabilitar botones"""
        state = 'normal' if enabled else 'disabled'
        buttons = [
            self.btn_registrar, self.btn_consultar, self.btn_eliminar, 
            self.btn_estadisticas, self.btn_lista_alumnos, self.btn_backup
        ]
        
        for btn in buttons:
            if hasattr(self, btn._name if hasattr(btn, '_name') else 'btn'):
                btn.config(state=state)
        
        # Actualizar indicador de conexión
        if enabled:
            self.connection_indicator.config(fg='#27ae60')  # Verde
            self.status_text.config(text="Sistema conectado y operativo")
        else:
            self.connection_indicator.config(fg='#e74c3c')  # Rojo
            self.status_text.config(text="Sistema desconectado")
    
    def buscar_arduino(self):
        """Buscar Arduino en un hilo separado"""
        def buscar():
            self.log_message("Buscando lector RFID...")
            puerto, estado = self.encontrar_puerto_arduino()
            
            if puerto:
                self.puerto = puerto
                # Establecer conexión serial persistente
                if self.abrir_conexion_serial():
                    self.root.after(0, lambda: self.status_label.config(
                        text=f"Lector RFID conectado en {puerto}", fg='#27ae60'))
                    self.root.after(0, lambda: self.toggle_buttons(True))
                    self.log_message(f"Lector RFID conectado y listo en {puerto}", "SUCCESS")
                else:
                    self.root.after(0, lambda: self.status_label.config(
                        text="Error de conexión RFID", fg='#e74c3c'))
                    self.log_message("Error al establecer conexión con el lector RFID", "ERROR")
            else:
                self.root.after(0, lambda: self.status_label.config(
                    text="Lector RFID no encontrado", fg='#e74c3c'))
                self.log_message("No se encontró el lector RFID", "ERROR")
                messagebox.showerror("Error", "No se encontró el lector RFID.\nVerifica la conexión e intenta nuevamente.")
        
        threading.Thread(target=buscar, daemon=True).start()
    
    def encontrar_puerto_arduino(self):
        """Busca el puerto del Arduino"""
        puertos = [p.device for p in list_ports.comports()]
        if not puertos:
            return None, "no_ports_found"
        
        for puerto in puertos:
            try:
                if self.intentar_healthcheck_en_puerto(puerto):
                    return puerto, "found"
            except Exception as e:
                continue
        
        return None, "not_found"
    
    def intentar_healthcheck_en_puerto(self, port):
        """Intenta healthcheck en un puerto específico"""
        try:
            ser = serial.Serial(port, BAUD_RATE, timeout=0.1, write_timeout=1)
            time.sleep(SERIAL_OPEN_RESET_WAIT)
            
            try:
                ser.reset_input_buffer()
                ser.reset_output_buffer()
            except:
                pass
            
            payload = json.dumps(HEALTHCHECK_JSON).encode("utf-8") + b"\n"
            
            for i in range(HEALTHCHECK_ATTEMPTS):
                ser.write(payload)
                ser.flush()
                time.sleep(HEALTHCHECK_INTERVAL)
            
            start = time.time()
            while time.time() - start < HEALTHCHECK_TIMEOUT:
                try:
                    line = ser.readline().decode(errors="ignore").strip()
                    if line.startswith("{") and line.endswith("}"):
                        data = json.loads(line)
                        if isinstance(data, dict) and data.get("status") == "online":
                            ser.close()
                            return True
                except:
                    continue
            
            ser.close()
            return False
        except:
            return False
    
    def abrir_conexion_serial(self):
        """Abrir conexión serial persistente"""
        try:
            if self.serial_connection and self.serial_connection.is_open:
                self.serial_connection.close()
            
            self.serial_connection = serial.Serial(self.puerto, BAUD_RATE, timeout=0.1, write_timeout=1)
            time.sleep(2.0)  # Tiempo para que el Arduino se inicialice
            
            try:
                self.serial_connection.reset_input_buffer()
            except:
                pass
            
            self.log_message("Conexión serial establecida", "SUCCESS")
            return True
        except Exception as e:
            self.log_message(f"Error al abrir conexión serial: {e}", "ERROR")
            return False
    
    def cerrar_conexion_serial(self):
        """Cerrar conexión serial persistente"""
        try:
            if self.serial_connection and self.serial_connection.is_open:
                self.serial_connection.close()
                self.serial_connection = None
                self.log_message("Conexión serial cerrada", "INFO")
        except Exception as e:
            self.log_message(f"Error al cerrar conexión serial: {e}", "ERROR")
    
    def leer_uid(self, timeout_global=10):
        """Lee UID usando conexión serial persistente"""
        with self.connection_lock:
            try:
                # Verificar que la conexión esté activa
                if not self.serial_connection or not self.serial_connection.is_open:
                    if not self.abrir_conexion_serial():
                        raise Exception("No se pudo establecer conexión serial")
                
                # Limpiar buffer antes de leer
                try:
                    self.serial_connection.reset_input_buffer()
                except:
                    pass
                
                start = time.time()
                while time.time() - start < timeout_global:
                    try:
                        if self.serial_connection.in_waiting > 0:
                            line = self.serial_connection.readline().decode(errors="ignore").strip()
                            if line:
                                data = json.loads(line)
                                if isinstance(data, dict) and "uid" in data:
                                    return data["uid"]
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        # Si hay error de conexión, intentar reconectar
                        if "device" in str(e).lower() or "port" in str(e).lower():
                            self.log_message("Reconectando puerto serial...", "WARNING")
                            if not self.abrir_conexion_serial():
                                raise Exception("Perdida de conexión serial")
                        continue
                    
                    time.sleep(0.05)  # Pequeña pausa para no saturar la CPU
                
                raise TimeoutError("No se recibió UID")
            except Exception as e:
                raise e
    
    def on_closing(self):
        """Manejar el cierre de la aplicación"""
        try:
            self.log_message("Cerrando sistema...", "INFO")
            # Cerrar conexión serial
            self.cerrar_conexion_serial()
            # Cerrar base de datos
            if hasattr(self, 'conn'):
                self.conn.close()
            # Cerrar aplicación
            self.root.destroy()
        except Exception as e:
            self.log_message(f"Error al cerrar: {e}", "ERROR")
            self.root.destroy()
    
    def abrir_registro(self):
        """Abrir ventana de registro"""
        RegistroWindow(self)
    
    def abrir_consulta(self):
        """Abrir ventana de consulta"""
        ConsultaWindow(self)
    
    def abrir_eliminacion(self):
        """Abrir ventana de eliminación"""
        EliminacionWindow(self)
    
    def mostrar_estadisticas(self):
        """Mostrar estadísticas del sistema"""
        try:
            self.cursor.execute("SELECT COUNT(*) FROM alumnos")
            total_alumnos = self.cursor.fetchone()[0]
            
            self.cursor.execute("SELECT grupo, COUNT(*) FROM alumnos GROUP BY grupo ORDER BY grupo")
            grupos = self.cursor.fetchall()
            
            # Crear ventana de estadísticas
            stats_window = tk.Toplevel(self.root)
            stats_window.title("Estadísticas del Sistema")
            stats_window.geometry("400x300")
            stats_window.configure(bg='#f0f0f0')
            
            # Centrar ventana
            stats_window.transient(self.root)
            stats_window.grab_set()
            
            # Contenido
            frame = ttk.Frame(stats_window, padding="20")
            frame.pack(fill=tk.BOTH, expand=True)
            title = tk.Label(frame, text="Estadísticas del Sistema", 
                           font=self.font_title, bg='#f0f0f0')
            title.pack(pady=(0, 20))
            
            total_label = tk.Label(frame, text=f"Total de alumnos: {total_alumnos}", 
                                 font=self.font_normal, bg='#f0f0f0')
            total_label.pack(pady=5)
            
            if grupos:
                groups_label = tk.Label(frame, text="Alumnos por grupo:", 
                                      font=self.font_normal, bg='#f0f0f0')
                groups_label.pack(pady=(20, 10))
                
                for grupo, cantidad in grupos:
                    grupo_label = tk.Label(frame, text=f"  {grupo}: {cantidad} alumno(s)", 
                                         font=self.font_normal, bg='#f0f0f0')
                    grupo_label.pack(pady=2)
            
            close_btn = tk.Button(frame, text="Cerrar", command=stats_window.destroy,
                                bg='#95a5a6', fg='white', font=self.font_button)
            close_btn.pack(pady=20)
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al obtener estadísticas: {e}")

class RegistroWindow:
    def __init__(self, parent):
        self.parent = parent
        self.window = tk.Toplevel(parent.root)
        self.window.title("Registrar Nuevo Alumno")
        self.window.geometry("500x400")
        self.window.configure(bg='#f0f0f0')
        
        # Centrar ventana
        self.window.transient(parent.root)
        self.window.grab_set()
        
        self.create_widgets()
    
    def create_widgets(self):
        frame = ttk.Frame(self.window, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
          # Título
        title = tk.Label(frame, text="Registro de Nuevo Alumno", 
                        font=self.parent.font_title, bg='#f0f0f0')
        title.grid(row=0, column=0, columnspan=2, pady=(0, 20))
        
        # Campos
        tk.Label(frame, text="Nombre:", font=self.parent.font_normal, bg='#f0f0f0').grid(row=1, column=0, sticky=tk.W, pady=5)
        self.nombre_entry = ttk.Entry(frame, width=30, font=self.parent.font_normal)
        self.nombre_entry.grid(row=1, column=1, pady=5, sticky=(tk.W, tk.E))
        
        tk.Label(frame, text="Grupo:", font=self.parent.font_normal, bg='#f0f0f0').grid(row=2, column=0, sticky=tk.W, pady=5)
        self.grupo_entry = ttk.Entry(frame, width=30, font=self.parent.font_normal)
        self.grupo_entry.grid(row=2, column=1, pady=5, sticky=(tk.W, tk.E))
        
        tk.Label(frame, text="Número de Control:", font=self.parent.font_normal, bg='#f0f0f0').grid(row=3, column=0, sticky=tk.W, pady=5)
        self.control_entry = ttk.Entry(frame, width=30, font=self.parent.font_normal)
        self.control_entry.grid(row=3, column=1, pady=5, sticky=(tk.W, tk.E))
        
        # Status
        self.status_label = tk.Label(frame, text="Complete los datos y presione 'Leer Tarjeta'", 
                                   font=self.parent.font_normal, bg='#f0f0f0', fg='#7f8c8d')
        self.status_label.grid(row=4, column=0, columnspan=2, pady=20)
        
        # Botones
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=20)
        self.btn_leer = tk.Button(btn_frame, text="Leer Tarjeta", 
                                bg='#3498db', fg='white', font=self.parent.font_button,
                                command=self.leer_y_registrar)
        self.btn_leer.pack(side=tk.LEFT, padx=5)
        
        btn_cancelar = tk.Button(btn_frame, text="Cancelar", 
                               bg='#95a5a6', fg='white', font=self.parent.font_button,
                               command=self.window.destroy)
        btn_cancelar.pack(side=tk.LEFT, padx=5)
        
        # Configurar grid
        frame.grid_columnconfigure(1, weight=1)
        
        # Focus en primer campo
        self.nombre_entry.focus()
    
    def leer_y_registrar(self):
        # Validar campos
        nombre = self.nombre_entry.get().strip()
        grupo = self.grupo_entry.get().strip()
        control = self.control_entry.get().strip()
        
        if not nombre or not grupo or not control:
            messagebox.showerror("Error", "Todos los campos son obligatorios")
            return
        
        if not control.isdigit():
            messagebox.showerror("Error", "El número de control debe contener solo números")
            return

        # Leer tarjeta
        def leer_tarjeta():
            try:
                self.parent.root.after(0, lambda: self.status_label.config(
                    text="Acerque la tarjeta al lector...", fg='#f39c12'))
                self.parent.root.after(0, lambda: self.btn_leer.config(state='disabled'))
                
                uid = self.parent.leer_uid(timeout_global=30)
                
                # Registrar en base de datos
                try:
                    self.parent.cursor.execute(
                        "INSERT INTO alumnos (uid, nombre, grupo, control) VALUES (?, ?, ?, ?)",
                        (uid, nombre, grupo, control))
                    self.parent.conn.commit()
                    
                    self.parent.root.after(0, lambda: messagebox.showinfo(
                        "Éxito", f"¡Registro exitoso!\nAlumno: {nombre}\nUID: {uid}"))
                    self.parent.log_message(f"Alumno registrado: {nombre} - UID: {uid}", "SUCCESS")
                    self.parent.root.after(0, self.window.destroy)
                    
                except sqlite3.IntegrityError:
                    # Tarjeta ya existe
                    self.parent.cursor.execute("SELECT nombre, grupo, control FROM alumnos WHERE uid=?", (uid,))
                    alumno_existente = self.parent.cursor.fetchone()
                    
                    if alumno_existente:
                        nombre_existente, grupo_existente, control_existente = alumno_existente
                        respuesta = messagebox.askyesno(
                            "Tarjeta Duplicada", 
                            f"Esta tarjeta ya está registrada para:\n"
                            f"Nombre: {nombre_existente}\n"
                            f"Grupo: {grupo_existente}\n"
                            f"Control: {control_existente}\n\n"
                            f"¿Desea actualizar con los nuevos datos?")
                        
                        if respuesta:
                            self.parent.cursor.execute(
                                "UPDATE alumnos SET nombre=?, grupo=?, control=? WHERE uid=?",
                                (nombre, grupo, control, uid))
                            self.parent.conn.commit()
                            self.parent.root.after(0, lambda: messagebox.showinfo(
                                "Éxito", f"¡Datos actualizados!\nAlumno: {nombre}"))
                            self.parent.log_message(f"Datos actualizados para UID {uid}: {nombre}", "SUCCESS")
                            self.parent.root.after(0, self.window.destroy)
                        else:
                            self.parent.root.after(0, lambda: self.btn_leer.config(state='normal'))
                            self.parent.root.after(0, lambda: self.status_label.config(
                                text="Operación cancelada", fg='#e74c3c'))
                except TimeoutError:
                    self.parent.root.after(0, lambda: self.status_label.config(
                    text="Tiempo agotado. No se detectó tarjeta", fg='#e74c3c'))
                    self.parent.root.after(0, lambda: self.btn_leer.config(state='normal'))
            except Exception as e:
                self.parent.root.after(0, lambda: messagebox.showerror("Error", f"Error al leer tarjeta: {e}"))
                self.parent.root.after(0, lambda: self.btn_leer.config(state='normal'))
            finally:
                self.sincronizar_datos()
        
        threading.Thread(target=leer_tarjeta, daemon=True).start()

class ConsultaWindow:
    def __init__(self, parent):
        self.parent = parent
        self.window = tk.Toplevel(parent.root)
        self.window.title("Consultar Tarjeta")
        self.window.geometry("450x350")
        self.window.configure(bg='#f0f0f0')
        
        self.window.transient(parent.root)
        self.window.grab_set()
        
        # Variable para controlar la lectura automática
        self.reading_active = True
        
        self.create_widgets()
        
        # Iniciar lectura automática inmediatamente
        self.start_automatic_reading()
        
        # Configurar el evento de cierre
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)

    def create_widgets(self):
        frame = ttk.Frame(self.window, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
        
        title = tk.Label(frame, text="Consulta Automática de Tarjeta", 
                        font=self.parent.font_title, bg='#f0f0f0')
        title.pack(pady=(0, 20))
        
        # Indicador visual de estado
        status_frame = tk.Frame(frame, bg='#f0f0f0')
        status_frame.pack(pady=10)
        
        self.status_indicator = tk.Label(status_frame, text="●", 
                                       font=Font(size=20), bg='#f0f0f0', fg='#27ae60')
        self.status_indicator.pack(side=tk.LEFT, padx=5)
        
        self.status_label = tk.Label(status_frame, text="Listo para leer. Acerque su tarjeta...", 
                                   font=self.parent.font_normal, bg='#f0f0f0', fg='#27ae60')
        self.status_label.pack(side=tk.LEFT)
        
        # Área de resultados
        self.result_frame = ttk.LabelFrame(frame, text="Información del Alumno", padding="10")
        self.result_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.result_text = tk.Text(self.result_frame, height=8, width=40, 
                                 font=self.parent.font_normal, state='disabled')
        self.result_text.pack(fill=tk.BOTH, expand=True)
        
        # Botones
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=20)
        
        self.btn_toggle = tk.Button(btn_frame, text="Pausar Lectura", 
                                  bg='#f39c12', fg='white', font=self.parent.font_button,
                                  command=self.toggle_reading)
        self.btn_toggle.pack(side=tk.LEFT, padx=5)
        
        btn_limpiar = tk.Button(btn_frame, text="Limpiar", 
                              bg='#95a5a6', fg='white', font=self.parent.font_button,
                              command=self.clear_results)
        btn_limpiar.pack(side=tk.LEFT, padx=5)
        
        btn_cerrar = tk.Button(btn_frame, text="Cerrar", 
                             bg='#e74c3c', fg='white', font=self.parent.font_button,
                             command=self.on_close)
        btn_cerrar.pack(side=tk.LEFT, padx=5)

    def start_automatic_reading(self):
        """Iniciar la lectura automática de tarjetas"""
        def read_loop():
            while self.reading_active:
                try:
                    if not hasattr(self, 'window') or not self.window.winfo_exists():
                        break
                    
                    # Verificar que hay conexión serial activa
                    if not self.parent.serial_connection or not self.parent.serial_connection.is_open:
                        self.parent.root.after(0, lambda: self.update_status(
                            "Reestableciendo conexión...", '#f39c12', '◐'))
                        if not self.parent.abrir_conexion_serial():
                            self.parent.root.after(0, lambda: self.update_status(
                                "Sin conexión serial", '#e74c3c', '●'))
                            time.sleep(2)
                            continue
                    
                    # Actualizar estado visual
                    self.parent.root.after(0, lambda: self.update_status(
                        "Listo para leer. Acerque su tarjeta...", '#27ae60', '●'))
                    
                    # Leer UID con timeout corto para mantener responsividad
                    uid = self.parent.leer_uid(timeout_global=0.5)  # Timeout más corto
                    
                    if uid and self.reading_active:
                        self.process_card(uid)
                        # Pausa después de procesar una tarjeta para evitar lecturas múltiples
                        time.sleep(2)
                    
                except TimeoutError:
                    # Timeout normal, continuar el bucle
                    continue
                except Exception as e:
                    if self.reading_active:
                        self.parent.root.after(0, lambda: self.update_status(
                            f"Error: {str(e)[:30]}...", '#e74c3c', '●'))
                        time.sleep(1)
                
                # Pequeña pausa para no saturar el sistema
                time.sleep(0.1)
        
        threading.Thread(target=read_loop, daemon=True).start()
    
    def process_card(self, uid):
        """Procesar la tarjeta leída"""
        def process():
            try:
                # Actualizar estado visual
                self.parent.root.after(0, lambda: self.update_status(
                    "Procesando tarjeta...", '#f39c12', '◐'))
                
                # Buscar en base de datos
                self.parent.cursor.execute("SELECT nombre, grupo, control FROM alumnos WHERE uid=?", (uid,))
                alumno = self.parent.cursor.fetchone()
                
                timestamp = datetime.now().strftime("%H:%M:%S")
                
                if alumno:
                    nombre, grupo, control = alumno
                    resultado = f"[{timestamp}] TARJETA ENCONTRADA\n"
                    resultado += f"Nombre: {nombre}\n"
                    resultado += f"Grupo: {grupo}\n"
                    resultado += f"Control: {control}\n"
                    resultado += f"UID: {uid}\n"
                    resultado += "-" * 30 + "\n"
                    
                    self.parent.log_message(f"Consulta automática exitosa - Alumno: {nombre}", "SUCCESS")
                    
                    self.parent.root.after(0, lambda: self.update_status(
                        f"¡Tarjeta encontrada! {nombre}", '#27ae60', '●'))
                else:
                    resultado = f"[{timestamp}] TARJETA NO REGISTRADA\n"
                    resultado += f"UID: {uid}\n"
                    resultado += "-" * 30 + "\n"
                    
                    self.parent.log_message(f"Tarjeta no registrada (automático) - UID: {uid}", "WARNING")
                    
                    self.parent.root.after(0, lambda: self.update_status(
                        "Tarjeta no registrada", '#f39c12', '●'))
                
                # Actualizar resultados
                def actualizar_resultado():
                    if hasattr(self, 'result_text'):
                        self.result_text.config(state='normal')
                        # Insertar al inicio para mostrar la lectura más reciente arriba
                        self.result_text.insert(1.0, resultado)
                        self.result_text.config(state='disabled')
                        # Scroll al top para mostrar el resultado más reciente
                        self.result_text.see(1.0)
                
                self.parent.root.after(0, actualizar_resultado)
                
            except Exception as e:
                self.parent.root.after(0, lambda: self.update_status(
                    f"Error: {str(e)[:20]}...", '#e74c3c', '●'))
        
        threading.Thread(target=process, daemon=True).start()
    
    def update_status(self, text, color, indicator):
        """Actualizar el estado visual"""
        try:
            if hasattr(self, 'status_label') and hasattr(self, 'status_indicator'):
                self.status_label.config(text=text, fg=color)
                self.status_indicator.config(fg=color, text=indicator)
        except:
            pass
    
    def toggle_reading(self):
        """Alternar entre activar/pausar la lectura automática"""
        self.reading_active = not self.reading_active
        
        if self.reading_active:
            self.btn_toggle.config(text="Pausar Lectura", bg='#f39c12')
            self.update_status("Lectura reactivada. Acerque su tarjeta...", '#27ae60', '●')
            self.start_automatic_reading()
        else:
            self.btn_toggle.config(text="Reanudar Lectura", bg='#27ae60')
            self.update_status("Lectura pausada", '#95a5a6', '○')
    
    def clear_results(self):
        """Limpiar los resultados mostrados"""
        self.result_text.config(state='normal')
        self.result_text.delete(1.0, tk.END)
        self.result_text.config(state='disabled')
    
    def on_close(self):
        """Manejar el cierre de la ventana"""
        self.reading_active = False
        time.sleep(0.2)  # Dar tiempo a que termine el hilo de lectura
        self.window.destroy()

class EliminacionWindow:
    def __init__(self, parent):
        self.parent = parent
        self.window = tk.Toplevel(parent.root)
        self.window.title("Eliminar Tarjeta")
        self.window.geometry("400x350")
        self.window.configure(bg='#f0f0f0')
        
        self.window.transient(parent.root)
        self.window.grab_set()
        
        self.alumno_info = None
        self.uid_eliminar = None
        
        self.create_widgets()
    
    def create_widgets(self):
        frame = ttk.Frame(self.window, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
        title = tk.Label(frame, text="Eliminar Tarjeta", 
                        font=self.parent.font_title, bg='#f0f0f0', fg='#e74c3c')
        title.pack(pady=(0, 20))
        
        warning = tk.Label(frame, text="ATENCIÓN: Esta acción no se puede deshacer", 
                         font=self.parent.font_normal, bg='#f0f0f0', fg='#e74c3c')
        warning.pack(pady=10)
        
        self.status_label = tk.Label(frame, text="Presione 'Leer Tarjeta' para identificar al alumno", 
                                   font=self.parent.font_normal, bg='#f0f0f0', fg='#7f8c8d')
        self.status_label.pack(pady=10)
        
        # Área de información del alumno
        self.info_frame = ttk.LabelFrame(frame, text="Información del Alumno", padding="10")
        self.info_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.info_text = tk.Text(self.info_frame, height=6, width=40, 
                               font=self.parent.font_normal, state='disabled')
        self.info_text.pack(fill=tk.BOTH, expand=True)
        
        # Botones
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=20)
        
        self.btn_leer = tk.Button(btn_frame, text="Leer Tarjeta", 
                                bg='#f39c12', fg='white', font=self.parent.font_button,
                                command=self.leer_tarjeta)
        self.btn_leer.pack(side=tk.LEFT, padx=5)
        
        self.btn_eliminar = tk.Button(btn_frame, text="ELIMINAR", 
                                    bg='#e74c3c', fg='white', font=self.parent.font_button,
                                    command=self.confirmar_eliminacion, state='disabled')
        self.btn_eliminar.pack(side=tk.LEFT, padx=5)
        
        btn_cancelar = tk.Button(btn_frame, text="Cancelar", 
                               bg='#95a5a6', fg='white', font=self.parent.font_button,
                               command=self.window.destroy)
        btn_cancelar.pack(side=tk.LEFT, padx=5)

    def leer_tarjeta(self):
        def leer():
            try:
                self.parent.root.after(0, lambda: self.status_label.config(
                    text="Acerque la tarjeta al lector...", fg='#f39c12'))
                self.parent.root.after(0, lambda: self.btn_leer.config(state='disabled'))
                
                uid = self.parent.leer_uid(timeout_global=20)
                
                # Buscar en base de datos
                self.parent.cursor.execute("SELECT nombre, grupo, control FROM alumnos WHERE uid=?", (uid,))
                alumno = self.parent.cursor.fetchone()
                
                if alumno:
                    self.uid_eliminar = uid
                    self.alumno_info = alumno
                    nombre, grupo, control = alumno
                    
                    info_text = f"Nombre: {nombre}\nGrupo: {grupo}\nControl: {control}\nUID: {uid}\n\nEste alumno será eliminado del sistema"
                    
                    def actualizar_info():
                        self.info_text.config(state='normal')
                        self.info_text.delete(1.0, tk.END)
                        self.info_text.insert(1.0, info_text)
                        self.info_text.config(state='disabled')
                        self.btn_eliminar.config(state='normal')
                        self.btn_leer.config(state='normal')
                        self.status_label.config(text="Tarjeta identificada. Confirme la eliminación", fg='#e74c3c')
                    
                    self.parent.root.after(0, actualizar_info)
                else:
                    self.parent.root.after(0, lambda: self.status_label.config(
                        text="Tarjeta no registrada", fg='#f39c12'))
                    self.parent.root.after(0, lambda: self.btn_leer.config(state='normal'))
                    
            except TimeoutError:
                self.parent.root.after(0, lambda: self.status_label.config(
                    text="Tiempo agotado", fg='#e74c3c'))
                self.parent.root.after(0, lambda: self.btn_leer.config(state='normal'))
            except Exception as e:
                self.parent.root.after(0, lambda: messagebox.showerror("Error", f"Error: {e}"))
                self.parent.root.after(0, lambda: self.btn_leer.config(state='normal'))
        
        threading.Thread(target=leer, daemon=True).start()
    
    def confirmar_eliminacion(self):
        if not self.alumno_info or not self.uid_eliminar:
            return
        nombre = self.alumno_info[0]
        respuesta = messagebox.askyesno(
            "Confirmar Eliminación",
            f"¿Está seguro de que desea eliminar permanentemente a:\n\n"
            f"{nombre}\n\n"
            f"Esta acción NO se puede deshacer.",
            icon='warning')
        
        if respuesta:
            try:
                self.parent.cursor.execute("DELETE FROM alumnos WHERE uid=?", (self.uid_eliminar,))
                self.parent.conn.commit()
                
                messagebox.showinfo("Éxito", f"Alumno {nombre} eliminado exitosamente")
                self.parent.log_message(f"Alumno eliminado: {nombre} - UID: {self.uid_eliminar}", "SUCCESS")
                self.window.destroy()
                
            except Exception as e:
                messagebox.showerror("Error", f"Error al eliminar: {e}")

def main():
    root = tk.Tk()
    app = RFIDSystem(root)
    root.mainloop()

if __name__ == "__main__":
    main()