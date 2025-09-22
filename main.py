import sqlite3
import serial
import time

# Configuración del puerto serie (ajusta el COM o /dev/tty según tu sistema)
SERIAL_PORT = "COM8"   # o "/dev/ttyUSB0" en Linux
BAUD_RATE = 9600

# Conectar a la base de datos (se crea si no existe)
conn = sqlite3.connect("alumnos.db")
cursor = conn.cursor()

# Crear tabla si no existe
cursor.execute("""
CREATE TABLE IF NOT EXISTS alumnos (
    uid TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    grupo TEXT NOT NULL,
    control TEXT NOT NULL
)
""")
conn.commit()

def leer_uid():
    """Espera un UID válido del lector RFID por serial"""
    with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as ser:
        print("Acerca la tarjeta al lector...")
        while True:
            line = ser.readline().decode().strip()
            if line.startswith("{\"uid\":"):
                try:
                    uid = line.split("\"uid\":\"")[1].split("\"")[0]
                    return uid
                except IndexError:
                    pass

def registrar_alumno():
    nombre = input("Nombre: ")
    grupo = input("Grupo: ")
    control = input("Número de control: ")
    uid = leer_uid()

    try:
        cursor.execute("INSERT INTO alumnos (uid, nombre, grupo, control) VALUES (?, ?, ?, ?)",
                       (uid, nombre, grupo, control))
        conn.commit()
        print(f"Alumno {nombre} registrado con UID {uid}")
    except sqlite3.IntegrityError:
        print("Error: esa tarjeta ya está registrada.")

def consultar_tarjeta():
    uid = leer_uid()
    cursor.execute("SELECT nombre, grupo, control FROM alumnos WHERE uid=?", (uid,))
    alumno = cursor.fetchone()
    if alumno:
        nombre, grupo, control = alumno
        print(f"Tarjeta {uid} pertenece a {nombre} | Grupo: {grupo} | Control: {control}")
    else:
        print(f"Tarjeta {uid} no está registrada en la base de datos.")

# Menú principal
while True:
    print("\n1. Registrar alumno")
    print("2. Consultar tarjeta")
    print("3. Salir")
    opcion = input("Elige opción: ")
    if opcion == "1":
        registrar_alumno()
    elif opcion == "2":
        consultar_tarjeta()
    elif opcion == "3":
        break
    else:
        print("Opción no válida")
