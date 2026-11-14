# MICrONS · Explorador de conexiones

Prototipo local y gratuito para consultar desde un ID de neurona sus socios, con sinapsis de entrada y salida en la misma tabla, anotaciones y exportación CSV.

## Requisitos

- Windows y Python 3.10 o posterior.
- Internet para consultar los servicios públicos de MICrONS/CAVE.
- Cuenta y token CAVE para el datastack público `minnie65_public`.

La aplicación no envía datos a un servidor propio ni necesita una clave de IA. Las consultas recuperan únicamente las sinapsis de la neurona seleccionada.

## Primer inicio

1. Instala Python si no está instalado: https://www.python.org/downloads/windows/ (activa “Add Python to PATH”).
2. Entra en CAVE con una cuenta Google asociada y acepta las condiciones de acceso al conjunto: https://global.daf-apis.com/
3. Abre PowerShell en esta carpeta y ejecuta el comando para iniciar la creación del token:

   ```powershell
   .\.venv\Scripts\python.exe -c "from caveclient import CAVEclient; c=CAVEclient(); c.auth.setup_token(make_new=True)"
   ```

   Se abrirá CAVE en el navegador para iniciar sesión y generar el token. Copia el token de esa página y guárdalo localmente ejecutando:

   ```powershell
   .\.venv\Scripts\python.exe -c "from caveclient import CAVEclient; c=CAVEclient(); token=input('Pega aquí el token de CAVE: ').strip(); c.auth.save_token(token=token)"
   ```

   No compartas el token. Se guarda en la configuración local de CAVE, no en los archivos del proyecto.
4. Haz doble clic en `INICIAR.bat`. La primera vez instalará las bibliotecas gratuitas y abrirá la app en el navegador.

Se inicia también desde PowerShell con `.\.venv\Scripts\python.exe -m streamlit run app.py`.

## Uso

- Pega un `pt_root_id`; el ejemplo inicial pertenece al tutorial oficial.
- La app consulta conexiones de entrada y salida y ordena los socios por total de sinapsis.
- Filtra por clase celular, estado de proofreading y texto del tipo celular (por ejemplo, `BC` o `23P`).
- Activa el enriquecimiento para añadir clasificaciones y estado/estrategia de proofreading a los socios.
- Genera un enlace de Neuroglancer para ver la neurona consultada y sus entradas/salidas en 3D.
- Exporta a CSV la lista resultante después de aplicar los filtros.

Generar la vista 3D guarda un estado visual (IDs y ubicaciones de sinapsis) en el servicio público de estados Neuroglancer de MICrONS para que el enlace pueda abrirse y compartirse.
- Consulta y descarga los resultados como CSV.

Las consultas usan la última materialización pública disponible en CAVE. Los socios se cuentan por número de sinapsis; este valor no equivale directamente a fuerza funcional. Para consistencia en análisis científicos, registra la versión de materialización indicada por la app.

## Fuentes

- Portal: https://www.microns-explorer.org/cortical-mm3
- Configuración CAVE: https://tutorial.microns-explorer.org/quickstart_notebooks/01-caveclient-setup.html
- Consulta de sinapsis: https://tutorial.microns-explorer.org/quickstart_notebooks/04-cave-query-synapses.html
