# Informe Pauta Haku

Informe de leads y costo por lead de Meta Ads, por sociedad y zona. Se actualiza solo todos los días a las 6 a. m. (hora Colombia) y se publica en GitHub Pages. Abre directo, sin clave: cualquiera con el enlace puede verlo. Para pedir clave, agrega el secreto opcional `INFORME_PIN`.

## Cómo funciona

1. `scripts/actualizar.py` consulta la API de Meta (cuentas en `config/cuentas.json`) y trae gasto, impresiones, alcance, clics y leads por conjunto de anuncios y por día, desde el 1 de enero.
2. Reparte cada conjunto en **sociedad**, **zona** y **canal** según `config/reglas.json` (y las correcciones de `config/asignaciones.csv`).
3. Cifra los datos con el PIN (AES-256, PBKDF2) y genera `salida/sitio/index.html` desde `web/plantilla.html`.
4. `.github/workflows/actualizar.yml` hace todo eso cada mañana y publica la página. Los datos sin cifrar nunca se suben al repositorio.

## Puesta en marcha (una sola vez)

1. **Secretos**: en el repositorio → *Settings* → *Secrets and variables* → *Actions* → *New repository secret*:
   - `META_TOKEN`: el token del usuario del sistema *Marcela Cossio* (app HAKU IA, permiso `ads_read`).
   - `INFORME_PIN` (opcional): solo si quieres que pida clave. Usa **8 caracteres o más**, porque el archivo cifrado es público y una clave corta se adivina probando.
2. **Pages**: *Settings* → *Pages* → *Build and deployment* → *Source*: **GitHub Actions**.
3. **Primera corrida**: pestaña *Actions* → *Actualizar informe* → *Run workflow*. Al terminar (2–5 min) el enlace aparece en el paso *publicar*.

## Revisar la agrupación

Cada corrida deja descargable el archivo **conjuntos** (en *Actions* → la corrida → *Artifacts*). Es una lista de todos los conjuntos con la sociedad, zona y canal que se les asignó.

- Si una sociedad no se reconoce, agrega su nombre a `patrones` en `config/reglas.json`.
- Para corregir un conjunto puntual, copia su `conjunto_id` en `config/asignaciones.csv` y escribe la sociedad, zona o canal correctos (lo que dejes vacío se sigue calculando solo).

## Probar sin Meta

```bash
pip install -r requirements.txt
python scripts/actualizar.py --demo
# abre salida/sitio/index.html
```

## Si algo falla

- *Error de Meta (190)*: el token venció o se revocó. Genera uno nuevo y reemplaza el secreto `META_TOKEN`.
- *Meta no devolvió datos*: el usuario del sistema no tiene acceso a esas cuentas publicitarias (Business Manager → Usuarios del sistema → Asignar activos).
- La versión de la API está en `config/cuentas.json` (`version_api`). Meta retira versiones cada ~2 años; si avisa que la versión ya no existe, súbela.
