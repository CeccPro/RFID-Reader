#include <SPI.h>
#include <MFRC522.h>

#define RST_PIN  9    // Pin 9 para el reset del RC522
#define SS_PIN   10   // Pin 10 para el SS (SDA) del RC522
MFRC522 mfrc522(SS_PIN, RST_PIN); // Creamos el objeto para el RC522

// Tiempo máximo que esperará readStringUntil('\n') si no hay newline (ms)
const unsigned long SERIAL_READ_TIMEOUT = 200;

// Función para verificar la conectividad completa del sensor
bool testSensorConnectivity() {
  // Test 1: Verificar versión del chip
  byte version = mfrc522.PCD_ReadRegister(mfrc522.VersionReg);
  if (version == 0x00 || version == 0xFF) {
    Serial.println("{\"test\":\"version_check\",\"result\":\"failed\"}");
    return false;
  }
  Serial.println("{\"test\":\"version_check\",\"result\":\"passed\",\"version\":\"0x" + String(version, HEX) + "\"}");
  
  // Test 2: Verificar comunicación SPI
  mfrc522.PCD_WriteRegister(mfrc522.TModeReg, 0x8D);
  byte testValue = mfrc522.PCD_ReadRegister(mfrc522.TModeReg);
  if (testValue != 0x8D) {
    Serial.println("{\"test\":\"spi_communication\",\"result\":\"failed\"}");
    return false;
  }
  Serial.println("{\"test\":\"spi_communication\",\"result\":\"passed\"}");
  
  // Test 3: Realizar auto-test del MFRC522 (opcional)
  bool autoTestResult = mfrc522.PCD_PerformSelfTest();
  if (!autoTestResult) {
    Serial.println("{\"test\":\"self_test\",\"result\":\"failed\",\"note\":\"Self-test failed but sensor may still work\"}");
  } else {
    Serial.println("{\"test\":\"self_test\",\"result\":\"passed\"}");
  }
  
  // Reiniciar el sensor después del auto-test
  mfrc522.PCD_Init();
  
  return true;
}

// --- Manejo de comandos por Serial ---
// Detecta líneas JSON entrantes y responde al healthcheck.
// No usa ArduinoJson para no complicar dependencias; hace match por substring.
void handleSerialCommands() {
  if (Serial.available() > 0) {
    // Leemos hasta newline o timeout pequeño
    String line = Serial.readStringUntil('\n');
    line.trim(); // quitar espacios y \r
    if (line.length() == 0) return;

    // Buscamos el healthcheck (acepta tanto "healtcheck":1 como "healtcheck": 1)
    if (line.indexOf("\"healtcheck\"") != -1) {
      // Checamos si hay un 1 tras la palabra (básico pero efectivo)
      int idx = line.indexOf("\"healtcheck\"");
      String sub = line.substring(idx);
      if (sub.indexOf("1") != -1) {
        Serial.println("{\"status\":\"online\"}");
        // No return; seguimos ejecutando por si hay tarjeta pegada al mismo tiempo
      }
    }
  }
}

void setup() {
  Serial.begin(9600);
  Serial.setTimeout(SERIAL_READ_TIMEOUT); // para readStringUntil
  SPI.begin();        // Iniciamos el Bus SPI
  mfrc522.PCD_Init(); // Iniciamos el MFRC522
  
  // Ejecutamos pruebas de conectividad completas
  Serial.println("{\"info\":\"Running connectivity tests\"}");
  if (!testSensorConnectivity()) {
    Serial.println("{\"error\":\"Sensor connectivity test failed\"}");
    Serial.println("{\"debug\":\"Check wiring, power supply and connections\"}");
    Serial.println("{\"status\":\"ERROR\"}");
    while(true); // Detenemos el programa
  }
  
  Serial.println("{\"status\":\"OK\"}");
}

void loop() {
  // Primero procesamos cualquier comando por serial (healthcheck)
  handleSerialCommands();

  // Luego revisamos si hay nuevas tarjetas presentes
  if (mfrc522.PICC_IsNewCardPresent()) {  
    // Debug: Tarjeta detectada
    Serial.println("{\"debug\":\"Card detected\"}");
      
    // Seleccionamos una tarjeta
    if (mfrc522.PICC_ReadCardSerial()) {
      // Debug: Lectura exitosa
      Serial.println("{\"debug\":\"Card read successfully\"}");
                  
      // Construimos el UID como string hexadecimal
      String uid = "";
      for (byte i = 0; i < mfrc522.uid.size; i++) {
        if (mfrc522.uid.uidByte[i] < 0x10) uid += "0";
        uid += String(mfrc522.uid.uidByte[i], HEX);
      }
      uid.toUpperCase(); // Convertir a mayúsculas
                  
      // Enviamos el JSON por serial
      Serial.println("{\"uid\":\"" + uid + "\"}");
                  
      // Terminamos la lectura de la tarjeta actual
      mfrc522.PICC_HaltA();
                  
      // Pequeño delay para evitar lecturas múltiples
      delay(1000);
    } else {
      // Debug: Error en la lectura
      Serial.println("{\"debug\":\"Failed to read card\"}");
    }
  }

  // Un pequeño delay no bloqueante para evitar saturar el loop
  delay(5);
}
