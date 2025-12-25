#include <Arduino.h>
#include <FFat.h>

void listDir(fs::FS &fs, const char *dirname, uint8_t levels) {
    Serial.printf("Listing directory: %s\n", dirname);

    File root = fs.open(dirname);
    if (!root) {
        Serial.println("Failed to open directory");
        return;
    }
    if (!root.isDirectory()) {
        Serial.println("Not a directory");
        return;
    }

    File file = root.openNextFile();
    while (file) {
        if (file.isDirectory()) {
            Serial.print("  DIR : ");
            Serial.println(file.name());
            if (levels) {
                listDir(fs, file.path(), levels - 1);
            }
        } else {
            Serial.print("  FILE: ");
            Serial.print(file.name());
            Serial.print("  SIZE: ");
            Serial.println(file.size());
        }
        file = root.openNextFile();
    }
}

void readFile(fs::FS &fs, const char *path) {
    Serial.printf("Reading file: %s\n", path);

    File file = fs.open(path);
    if (!file) {
        Serial.println("Failed to open file for reading");
        return;
    }

    Serial.print("Read from file: ");
    while (file.available()) {
        Serial.write(file.read());
    }
    file.close();
}

void writeFile(fs::FS &fs, const char *path, const char *message) {
    Serial.printf("Writing file: %s\n", path);

    File file = fs.open(path, FILE_WRITE);
    if (!file) {
        Serial.println("Failed to open file for writing");
        return;
    }
    if (file.print(message)) {
        Serial.println("File written");
    } else {
        Serial.println("Write failed");
    }
    file.close();
}

void appendFile(fs::FS &fs, const char *path, const char *message) {
    Serial.printf("Appending to file: %s\n", path);

    File file = fs.open(path, FILE_APPEND);
    if (!file) {
        Serial.println("Failed to open file for appending");
        return;
    }
    if (file.print(message)) {
        Serial.println("Message appended");
    } else {
        Serial.println("Append failed");
    }
    file.close();
}

void deleteFile(fs::FS &fs, const char *path) {
    Serial.printf("Deleting file: %s\n", path);
    if (fs.remove(path)) {
        Serial.println("File deleted");
    } else {
        Serial.println("Delete failed");
    }
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    
    Serial.println("\n\n=== FatFS Test ===\n");

    // FatFS mounten
    if (!FFat.begin(true)) {
        Serial.println("FFat Mount Failed");
        return;
    }

    uint64_t cardSize = FFat.totalBytes();
    Serial.printf("FFat Size: %llu MB\n", cardSize / (1024 * 1024));
    Serial.printf("FFat Used: %llu MB\n", FFat.usedBytes() / (1024 * 1024));
    Serial.printf("FFat Free: %llu MB\n\n", (cardSize - FFat.usedBytes()) / (1024 * 1024));

    // Dateien auflisten
    listDir(FFat, "/", 2);
    Serial.println();

    // Datei aus data/ Verzeichnis lesen (falls vorhanden)
    if (FFat.exists("/test.txt")) {
        readFile(FFat, "/test.txt");
        Serial.println();
    }

    // Neue Datei schreiben
    writeFile(FFat, "/hello.txt", "Hello from ESP32!\n");
    readFile(FFat, "/hello.txt");
    Serial.println();

    // An Datei anhängen
    appendFile(FFat, "/hello.txt", "This is appended text.\n");
    readFile(FFat, "/hello.txt");
    Serial.println();

    // Datei löschen
    deleteFile(FFat, "/hello.txt");
    Serial.println();

    // Finale Auflistung
    Serial.println("Final directory listing:");
    listDir(FFat, "/", 2);

    Serial.println("\n=== Test Complete ===");
}

void loop() {
    delay(10000);
}
