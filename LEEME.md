# Resultados de Loterías F-26

- **App web:** `index.html` (lee `data/hoy.json` cada minuto y `data/historial.json` una vez).
- **Robot:** `robot.py`, corre solo en GitHub Actions (`.github/workflows/robot.yml`) después de cada sorteo y cada 2 horas.
- **APK:** `android/`, se arma sola con `.github/workflows/apk.yml` y se publica en *Releases → apk*.

**Firma de la APK:** mientras estemos en prueba se usa `android/firma/prueba.jks` (pública). Antes de Play Store se creará una llave privada guardada en los secretos `KEYSTORE_B64` y `KEYSTORE_PASS`.
