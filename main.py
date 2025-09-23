#!/usr/bin/env python3
# main.py (versión con reintentos y espera al abrir puerto)
import json
import sqlite3
import time
import sys
import os
import logging
from datetime import datetime

BAUD_RATE = 9600
HEALTHCHECK_JSON = {"healtcheck": 1}
HEALTHCHECK_TIMEOUT = 2.5        # cuanto esperamos por respuesta
SERIAL_OPEN_RESET_WAIT = 2.0     # tiempo para que Arduino arranque después de abrir puerto
HEALTHCHECK_ATTEMPTS = 3         # cuántas veces enviar el healthcheck
HEALTHCHECK_INTERVAL = 0.15      # intervalo entre envíos
DB_FILE = "alumnos.db"
DEBUG = False  # Cambia a True para activar mensajes de debug

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('rfid_system.log'),
        logging.StreamHandler(sys.stdout) if DEBUG else logging.NullHandler()
    ]
)

# Colores para la terminal
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_colored(text, color=Colors.ENDC):
    """Imprime texto con color"""
    print(f"{color}{text}{Colors.ENDC}")

def print_header(text):
    """Imprime un encabezado con formato"""
    print("\n" + "=" * 50)
    print_colored(f" {text} ", Colors.HEADER + Colors.BOLD)
    print("=" * 50)

def print_success(text):
    """Imprime mensaje de éxito"""
    print_colored(f"✓ {text}", Colors.OKGREEN)

def print_error(text):
    """Imprime mensaje de error"""
    print_colored(f"✗ {text}", Colors.FAIL)

def print_warning(text):
    """Imprime mensaje de advertencia"""
    print_colored(f"⚠ {text}", Colors.WARNING)

def print_info(text):
    """Imprime mensaje informativo"""
    print_colored(f"ℹ {text}", Colors.OKCYAN)

def clear_screen():
    """Limpia la pantalla"""
    os.system('cls' if os.name == 'nt' else 'clear')

def get_valid_input(prompt, validator=None, error_msg="Entrada inválida. Intente nuevamente."):
    """Obtiene entrada válida del usuario"""
    while True:
        value = input(f"{Colors.OKBLUE}{prompt}{Colors.ENDC}").strip()
        if not value:
            print_error("Este campo no puede estar vacío.")
            continue
        if validator is None or validator(value):
            return value
        print_error(error_msg)

def show_menu():
    """Muestra el menú principal"""
    print_header("SISTEMA DE GESTIÓN RFID")
    print_colored("1. 📝 Registrar nuevo alumno", Colors.OKBLUE)
    print_colored("2. 🔍 Consultar tarjeta", Colors.OKBLUE)
    print_colored("3. 🗑️ Eliminar tarjeta", Colors.OKBLUE)
    print_colored("4. 📊 Ver estadísticas", Colors.OKBLUE)
    print_colored("5. ❌ Salir", Colors.OKBLUE)
    print("-" * 30)

def debug_print(message):
    """Imprime mensajes de debug solo si DEBUG está activo"""
    if DEBUG:
        print(message)

def log_error(message, exception=None):
    """Registra errores en el log del sistema"""
    error_msg = message
    if exception:
        error_msg += f" - {str(exception)}"
    logging.error(error_msg)
    debug_print(f"ERROR: {error_msg}")

def log_info(message):
    """Registra información en el log del sistema"""
    logging.info(message)
    debug_print(f"INFO: {message}")

def handle_critical_error(message, exception=None):
    """Maneja errores críticos del sistema"""
    log_error(message, exception)
    print_error(f"Error crítico: {message}")
    if exception:
        print_error(f"Detalles técnicos: {str(exception)}")
    print_warning("El sistema necesita cerrarse para evitar problemas.")
    input(f"\n{Colors.OKCYAN}Presiona Enter para salir...{Colors.ENDC}")
    sys.exit(1)



try:
    import serial
    import serial.tools.list_ports as list_ports
except ImportError as e:
    print_error("Error: La librería pyserial no está instalada.")
    print_info("Para instalar, ejecuta: pip install pyserial")
    log_error("pyserial import failed", e)
    input(f"\n{Colors.OKCYAN}Presiona Enter para salir...{Colors.ENDC}")
    sys.exit(1)
except Exception as e:
    handle_critical_error("Error inesperado al importar pyserial", e)

# DB setup
try:
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS alumnos (
        uid TEXT PRIMARY KEY,
        nombre TEXT NOT NULL,
        grupo TEXT NOT NULL,
        control TEXT NOT NULL
    )
    """)
    conn.commit()
    log_info("Base de datos inicializada correctamente")
except sqlite3.Error as e:
    handle_critical_error("Error al inicializar la base de datos", e)
except Exception as e:
    handle_critical_error("Error inesperado con la base de datos", e)

def listar_puertos_disponibles():
    """Lista todos los puertos seriales disponibles"""
    try:
        ports = list_ports.comports()
        return [p.device for p in ports]
    except Exception as e:
        log_error("Error al listar puertos seriales", e)
        return []

def intentar_healthcheck_en_puerto(port, healthcheck_json=HEALTHCHECK_JSON, timeout=HEALTHCHECK_TIMEOUT):
    """Intenta enviar el healthcheck y espera respuesta JSON con status:online"""
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=0.1, write_timeout=1)
    except Exception as e:
        return False, f"open_failed: {e}"

    try:
        # Al abrir el puerto, muchos Arduinos se reinician. Esperamos a que termine el boot.
        time.sleep(SERIAL_OPEN_RESET_WAIT)

        # Limpiamos buffers
        try:
            ser.reset_input_buffer()
            ser.reset_output_buffer()
        except Exception:
            pass

        payload_str = json.dumps(healthcheck_json) + "\n"
        payload = payload_str.encode("utf-8")        # Enviamos el healthcheck varias veces para asegurar recepción
        for i in range(HEALTHCHECK_ATTEMPTS):
            try:
                ser.write(payload)
                ser.flush()
                debug_print(f"DEBUG: sent healthcheck to {port}: {payload_str.strip()}")
            except Exception as e:
                ser.close()
                return False, f"write_failed: {e}"
            time.sleep(HEALTHCHECK_INTERVAL)        # Escuchamos durante `timeout` segundos
        start = time.time()
        while time.time() - start < timeout:
            try:
                line = ser.readline().decode(errors="ignore").strip()
            except Exception:
                line = ""
            if line == "":
                # para debug: impresiones vacías eran las que viste antes
                debug_print("DEBUG: read line:")
                continue
            debug_print("DEBUG: read line: " + line)
            if line.startswith("{") and line.endswith("}"):
                try:
                    data = json.loads(line)
                    if isinstance(data, dict) and data.get("status") == "online":
                        ser.close()
                        return True, "online"
                except json.JSONDecodeError:
                    pass
        return False, "no_response"
    finally:
        try:
            ser.close()
        except Exception:
            pass

def encontrar_puerto_arduino(timeout_por_puerto=HEALTHCHECK_TIMEOUT):
    puertos = listar_puertos_disponibles()
    if not puertos:
        log_error("No hay puertos seriales disponibles")
        return None, "no_ports_found"
    
    clear_screen()
    print_info("Buscando lector RFID...")
    for p in puertos:
        try:
            print(f"  Probando puerto {p}...")
            ok, info = intentar_healthcheck_en_puerto(p, timeout=timeout_por_puerto)
            debug_print(json.dumps({"probe_port": p, "result": info}))
            if ok:
                print_success(f"Lector de RFID encontrado en puerto {p}")
                log_info(f"Arduino encontrado en puerto {p}")
                return p, "found"
        except Exception as e:
            log_error(f"Error probando puerto {p}", e)
            continue
    
    log_error("No se encontró ningún dispositivo RFID")
    return None, "not_found"

def leer_uid_desde_puerto(port, timeout_global=10):
    """Lee UID desde puerto serial con manejo robusto de errores"""
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=0.1, write_timeout=1)
        log_info(f"Puerto {port} abierto para lectura de UID")
    except Exception as e:
        log_error(f"Error al abrir puerto {port}", e)
        raise RuntimeError(f"Error al abrir puerto {port}: {e}")
    
    try:
        # esperar un poco por si el Arduino acaba de resetear
        time.sleep(0.2)
        
        try:
            ser.reset_input_buffer()
        except Exception as e:
            log_error("Error al limpiar buffer de entrada", e)
        
        start = time.time()
        while time.time() - start < timeout_global:
            try:
                line = ser.readline().decode(errors="ignore").strip()
            except Exception as e:
                log_error("Error al leer línea del puerto serial", e)
                line = ""
                
            if not line:
                continue
                
            debug_print("DEBUG: read line: " + line)
            try:
                data = json.loads(line)
                if isinstance(data, dict) and "uid" in data:
                    log_info(f"UID leído exitosamente: {data['uid']}")
                    return data["uid"]
            except json.JSONDecodeError as e:
                debug_print(f"Error decodificando JSON: {e}")
                continue
                
        log_error("Timeout esperando UID")
        raise TimeoutError("No se recibió UID dentro del timeout.")
    finally:
        try:
            ser.close()
        except Exception as e:
            log_error("Error al cerrar puerto serial", e)

def registrar_alumno_con_lectura(port):
    print_header("REGISTRO DE NUEVO ALUMNO")
    
    # Validador para número de control (solo números)
    def validar_control(valor):
        return valor.isdigit()
    
    nombre = get_valid_input("Nombre del alumno: ")
    grupo = get_valid_input("Grupo: ")
    control = get_valid_input("Número de control: ", validar_control, "El número de control debe contener solo números.")
    print_info("Acerque la tarjeta al lector...")
    debug_print(json.dumps({"info": "waiting_for_card", "port": port}))
    
    try:
        uid = leer_uid_desde_puerto(port, timeout_global=30)
        print_success(f"Tarjeta leída: {uid}")
    except TimeoutError:
        print_error("Tiempo de espera agotado. No se detectó ninguna tarjeta.")
        return
    except Exception as e:
        print_error(f"Error al leer la tarjeta: {e}")
        debug_print(json.dumps({"error": "read_uid_failed", "detail": str(e)}))
        return
    
    try:
        cursor.execute("INSERT INTO alumnos (uid, nombre, grupo, control) VALUES (?, ?, ?, ?)",
                       (uid, nombre, grupo, control))
        conn.commit()
        debug_print(json.dumps({"status": "ok", "action": "register", "uid": uid, "nombre": nombre}))
        print_success(f"¡Registro exitoso! Alumno [{nombre}] registrado correctamente.")
        log_info(f"Alumno registrado: {nombre} - UID: {uid}")
    except sqlite3.IntegrityError:
        debug_print(json.dumps({"error": "uid_already_registered", "uid": uid}))
        print_warning("Esta tarjeta ya está registrada en el sistema.")
        log_info(f"Intento de registro duplicado - UID: {uid}")
        
        # Mostrar información del alumno existente
        try:
            cursor.execute("SELECT nombre, grupo, control FROM alumnos WHERE uid=?", (uid,))
            alumno = cursor.fetchone()
            if alumno:
                nombre_existente, grupo_existente, control_existente = alumno
                print_info(f"Registrada para: {nombre_existente} (Grupo: {grupo_existente}, Control: {control_existente})")
                
                # Ofrecer opciones al usuario
                print("\n" + "─" * 40)
                print_colored("¿Qué desea hacer?", Colors.HEADER)
                print_colored("1. Mantener datos existentes", Colors.OKBLUE)
                print_colored("2. Actualizar con nuevos datos", Colors.OKBLUE)
                print_colored("3. Cancelar operación", Colors.OKBLUE)
                
                while True:
                    opcion = input(f"{Colors.OKBLUE}➤ Seleccione una opción (1-3): {Colors.ENDC}").strip()
                    if opcion == "1":
                        print_info("Se mantuvieron los datos existentes.")
                        break
                    elif opcion == "2":
                        try:
                            cursor.execute("UPDATE alumnos SET nombre=?, grupo=?, control=? WHERE uid=?",
                                         (nombre, grupo, control, uid))
                            conn.commit()
                            print_success(f"¡Datos actualizados! Tarjeta ahora registrada para {nombre}.")
                            log_info(f"Datos actualizados para UID {uid}: {nombre_existente} -> {nombre}")
                        except sqlite3.Error as e:
                            log_error("Error al actualizar datos en la base de datos", e)
                            print_error(f"Error al actualizar: {e}")
                        break
                    elif opcion == "3":
                        print_info("Operación cancelada.")
                        break
                    else:
                        print_error("Opción inválida. Seleccione 1, 2 o 3.")
        except sqlite3.Error as e:
            log_error("Error al consultar información del alumno existente", e)
            print_error("No se pudo obtener información del alumno existente.")
    except sqlite3.Error as e:
        log_error("Error de base de datos durante el registro", e)
        print_error(f"Error de base de datos: {e}")
    except Exception as e:
        log_error("Error inesperado durante el registro", e)
        print_error(f"Error inesperado: {e}")
    
    input(f"\n{Colors.OKCYAN}Presiona Enter para continuar...{Colors.ENDC}")

def consultar_tarjeta_en_port(port):
    print_header("CONSULTA DE TARJETA")
    print_info("Acerque la tarjeta al lector...")
    debug_print(json.dumps({"info": "waiting_for_card", "port": port}))
    
    try:
        uid = leer_uid_desde_puerto(port, timeout_global=20)
        print_success(f"Tarjeta leída: {uid}")
    except TimeoutError:
        print_error("Tiempo de espera agotado. No se detectó ninguna tarjeta.")
        input(f"\n{Colors.OKCYAN}Presiona Enter para continuar...{Colors.ENDC}")
        return
    except Exception as e:
        print_error(f"Error al leer la tarjeta: {e}")
        debug_print(json.dumps({"error": "read_uid_failed", "detail": str(e)}))
        input(f"\n{Colors.OKCYAN}Presiona Enter para continuar...{Colors.ENDC}")
        return
    
    try:
        cursor.execute("SELECT nombre, grupo, control FROM alumnos WHERE uid=?", (uid,))
        alumno = cursor.fetchone()
        
        if alumno:
            nombre, grupo, control = alumno
            debug_print(json.dumps({"status": "found", "uid": uid, "nombre": nombre, "grupo": grupo, "control": control}))
            log_info(f"Consulta exitosa - Alumno: {nombre}")
            
            print("\n" + "─" * 40)
            print_colored("📋 INFORMACIÓN DEL ALUMNO", Colors.HEADER + Colors.BOLD)
            print("─" * 40)
            print_colored(f"👤 Nombre: {nombre}", Colors.OKGREEN)
            print_colored(f"📚 Grupo: {grupo}", Colors.OKGREEN)
            print_colored(f"🔢 Número de control: {control}", Colors.OKGREEN)
            print_colored(f"🔖 UID: {uid}", Colors.OKCYAN)
            print("─" * 40)
        else:
            debug_print(json.dumps({"status": "not_registered", "uid": uid}))
            log_info(f"Tarjeta no registrada consultada - UID: {uid}")
            print_warning("⚠ Tarjeta no registrada en el sistema.")
            print_info(f"UID: {uid}")
    except sqlite3.Error as e:
        log_error("Error de base de datos durante la consulta", e)
        print_error(f"Error al consultar la base de datos: {e}")
    except Exception as e:
        log_error("Error inesperado durante la consulta", e)
        print_error(f"Error inesperado: {e}")
    
    input(f"\n{Colors.OKCYAN}Presiona Enter para continuar...{Colors.ENDC}")

def eliminar_tarjeta(port):
    """Función para eliminar una tarjeta del sistema"""
    print_header("ELIMINAR TARJETA")
    print_info("Acerque la tarjeta que desea eliminar al lector...")
    debug_print(json.dumps({"info": "waiting_for_card_to_delete", "port": port}))
    
    try:
        uid = leer_uid_desde_puerto(port, timeout_global=20)
        print_success(f"Tarjeta leída: {uid}")
    except TimeoutError:
        print_error("Tiempo de espera agotado. No se detectó ninguna tarjeta.")
        input(f"\n{Colors.OKCYAN}Presiona Enter para continuar...{Colors.ENDC}")
        return
    except Exception as e:
        print_error(f"Error al leer la tarjeta: {e}")
        debug_print(json.dumps({"error": "read_uid_failed", "detail": str(e)}))
        input(f"\n{Colors.OKCYAN}Presiona Enter para continuar...{Colors.ENDC}")
        return
    
    try:
        # Verificar si la tarjeta existe
        cursor.execute("SELECT nombre, grupo, control FROM alumnos WHERE uid=?", (uid,))
        alumno = cursor.fetchone()
        
        if not alumno:
            print_warning("⚠ Esta tarjeta no está registrada en el sistema.")
            print_info(f"UID: {uid}")
            log_info(f"Intento de eliminar tarjeta no registrada - UID: {uid}")
            input(f"\n{Colors.OKCYAN}Presiona Enter para continuar...{Colors.ENDC}")
            return
        
        nombre, grupo, control = alumno
        print("\n" + "─" * 40)
        print_colored("📋 TARJETA A ELIMINAR", Colors.HEADER + Colors.BOLD)
        print("─" * 40)
        print_colored(f"👤 Nombre: {nombre}", Colors.WARNING)
        print_colored(f"📚 Grupo: {grupo}", Colors.WARNING)
        print_colored(f"🔢 Número de control: {control}", Colors.WARNING)
        print_colored(f"🔖 UID: {uid}", Colors.WARNING)
        print("─" * 40)
        
        # Confirmar eliminación
        print_warning("\n⚠ ATENCIÓN: Esta acción no se puede deshacer.")
        confirmacion = input(f"{Colors.FAIL}¿Está seguro de que desea eliminar esta tarjeta? (escriba 'ELIMINAR' para confirmar): {Colors.ENDC}").strip()
        
        if confirmacion == "ELIMINAR":
            cursor.execute("DELETE FROM alumnos WHERE uid=?", (uid,))
            conn.commit()
            print_success(f"✓ Tarjeta eliminada exitosamente.")
            print_info(f"Alumno {nombre} ha sido removido del sistema.")
            log_info(f"Tarjeta eliminada - Alumno: {nombre}, UID: {uid}")
            debug_print(json.dumps({"status": "deleted", "uid": uid, "nombre": nombre}))
        else:
            print_info("Eliminación cancelada. No se realizaron cambios.")
            log_info(f"Eliminación cancelada por el usuario - UID: {uid}")
            
    except sqlite3.Error as e:
        log_error("Error de base de datos durante la eliminación", e)
        print_error(f"Error al acceder a la base de datos: {e}")
    except Exception as e:
        log_error("Error inesperado durante la eliminación", e)
        print_error(f"Error inesperado: {e}")
    
    input(f"\n{Colors.OKCYAN}Presiona Enter para continuar...{Colors.ENDC}")

def mostrar_estadisticas():
    """Muestra estadísticas del sistema"""
    print_header("ESTADÍSTICAS DEL SISTEMA")
    
    try:
        # Total de alumnos registrados
        cursor.execute("SELECT COUNT(*) FROM alumnos")
        total_alumnos = cursor.fetchone()[0]
        
        # Alumnos por grupo
        cursor.execute("SELECT grupo, COUNT(*) FROM alumnos GROUP BY grupo ORDER BY grupo")
        grupos = cursor.fetchall()
        
        print_colored(f"📊 Total de alumnos registrados: {total_alumnos}", Colors.OKGREEN)
        
        if grupos:
            print("\n" + "─" * 30)
            print_colored("📚 Alumnos por grupo:", Colors.HEADER)
            print("─" * 30)
            for grupo, cantidad in grupos:
                print_colored(f"  {grupo}: {cantidad} alumno(s)", Colors.OKBLUE)
        else:
            print_info("No hay alumnos registrados aún.")
    except sqlite3.Error as e:
        log_error("Error al consultar estadísticas de la base de datos", e)
        print_error(f"Error al obtener estadísticas: {e}")
    except Exception as e:
        log_error("Error inesperado al mostrar estadísticas", e)
        print_error(f"Error inesperado: {e}")
    
    input(f"\n{Colors.OKCYAN}Presiona Enter para continuar...{Colors.ENDC}")

def main():
    """Función principal del sistema con manejo robusto de errores"""
    try:
        debug_print(json.dumps({"info": "scanning_ports"}))
        puerto, estado = encontrar_puerto_arduino()
        if not puerto:
            debug_print(json.dumps({"error": "arduino_not_found", "detail": estado}))
            print_error("Arduino no encontrado. Asegúrate de que esté conectado y el Monitor Serial cerrado.")
            print_info("Verifica que:")
            print_info("- El Arduino esté conectado correctamente")
            print_info("- El puerto serial no esté siendo usado por otra aplicación")
            print_info("- El código correcto esté cargado en el Arduino")
            input(f"\n{Colors.OKCYAN}Presiona Enter para salir...{Colors.ENDC}")
            return

        debug_print(json.dumps({"info": "arduino_found", "port": puerto}))
        log_info(f"Sistema iniciado correctamente con puerto {puerto}")

        while True:
            try:
                clear_screen()
                show_menu()
                opcion = input(f"{Colors.OKBLUE}➤ Seleccione una opción (1-5): {Colors.ENDC}").strip()
                
                if opcion == "1":
                    try:
                        registrar_alumno_con_lectura(puerto)
                    except Exception as e:
                        log_error("Error durante el registro de alumno", e)
                        print_error(f"Error durante el registro: {e}")
                        input(f"\n{Colors.OKCYAN}Presiona Enter para continuar...{Colors.ENDC}")
                elif opcion == "2":
                    try:
                        consultar_tarjeta_en_port(puerto)
                    except Exception as e:
                        log_error("Error durante la consulta de tarjeta", e)
                        print_error(f"Error durante la consulta: {e}")
                        input(f"\n{Colors.OKCYAN}Presiona Enter para continuar...{Colors.ENDC}")
                elif opcion == "3":
                    try:
                        eliminar_tarjeta(puerto)
                    except Exception as e:
                        log_error("Error durante la eliminación de tarjeta", e)
                        print_error(f"Error durante la eliminación: {e}")
                        input(f"\n{Colors.OKCYAN}Presiona Enter para continuar...{Colors.ENDC}")
                elif opcion == "4":
                    try:
                        mostrar_estadisticas()
                    except Exception as e:
                        log_error("Error al mostrar estadísticas", e)
                        print_error(f"Error al mostrar estadísticas: {e}")
                        input(f"\n{Colors.OKCYAN}Presiona Enter para continuar...{Colors.ENDC}")
                elif opcion == "5":
                    clear_screen()
                    debug_print(json.dumps({"info": "exiting"}))
                    print_success("¡Hasta luego!")
                    log_info("Sistema cerrado por el usuario")
                    time.sleep(1)
                    clear_screen()
                    break
                else:
                    print_error("Opción inválida. Por favor seleccione una opción del 1 al 5.")
                    input(f"\n{Colors.OKCYAN}Presiona Enter para continuar...{Colors.ENDC}")
                    debug_print(json.dumps({"error": "invalid_option", "option": opcion}))
            except KeyboardInterrupt:
                print_warning("\n\nInterrupción detectada. Cerrando sistema...")
                log_info("Sistema cerrado por interrupción del usuario")
                break
            except Exception as e:
                log_error("Error inesperado en el bucle principal", e)
                print_error(f"Error inesperado: {e}")
                print_warning("El sistema continuará funcionando...")
                input(f"\n{Colors.OKCYAN}Presiona Enter para continuar...{Colors.ENDC}")
    except Exception as e:
        handle_critical_error("Error crítico en la función principal", e)

if __name__ == "__main__":
    main()