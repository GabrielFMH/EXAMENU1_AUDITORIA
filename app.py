from openai import OpenAI
from flask import Flask, send_from_directory, request, jsonify, Response
import re
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


app = Flask(__name__)

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# Ruta para servir el index.html desde la carpeta dist
@app.route('/',  methods=["GET",'POST'])
def serve_index():
    return send_from_directory('dist', 'index.html')

# Ruta para servir los archivos estáticos generados
@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('dist', path)

client = OpenAI(
    base_url = 'http://localhost:11434/v1',
    api_key='ollama', # required, but unused
)

@app.route('/analizar-riesgos', methods=['POST'])
def analizar_riesgos():
    try:
        data = request.get_json()  # Obtener datos JSON enviados al endpoint
        if not data:
            return jsonify({"error": "Cuerpo de la solicitud debe ser JSON"}), 400
        activo = data.get('activo')  # Extraer el valor del activo
        if not activo or not isinstance(activo, str) or len(activo.strip()) == 0:
            return jsonify({"error": "El campo 'activo' es necesario y debe ser una cadena no vacía"}), 400

        riesgos, impactos = obtener_riesgos(activo.strip())  # Llamar a la función para obtener riesgos e impactos
        if not riesgos:
            return jsonify({"error": "No se pudieron generar riesgos para el activo proporcionado"}), 500
        return jsonify({"activo": activo, "riesgos": riesgos, "impactos": impactos})
    except Exception as e:
        logging.error(f"Error en /analizar-riesgos: {str(e)}")
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route('/sugerir-tratamiento', methods=['POST'])
def sugerir_tratamiento():
    try:
        data = request.get_json()  # Obtener datos JSON enviados al endpoint
        if not data:
            return jsonify({"error": "Cuerpo de la solicitud debe ser JSON"}), 400
        activo = data.get('activo')  # Extraer el valor del activo
        riesgo = data.get('riesgo')  # Extraer el valor del riesgo
        impacto = data.get('impacto')  # Extraer el valor del impacto

        # Verificar que todos los campos necesarios están presentes y válidos
        if not activo or not isinstance(activo, str) or len(activo.strip()) == 0:
            return jsonify({"error": "El campo 'activo' es necesario y debe ser una cadena no vacía"}), 400
        if not riesgo or not isinstance(riesgo, str) or len(riesgo.strip()) == 0:
            return jsonify({"error": "El campo 'riesgo' es necesario y debe ser una cadena no vacía"}), 400
        if not impacto or not isinstance(impacto, str) or len(impacto.strip()) == 0:
            return jsonify({"error": "El campo 'impacto' es necesario y debe ser una cadena no vacía"}), 400

        # Combinar riesgo e impacto para formar la entrada completa para obtener_tratamiento
        entrada_tratamiento = f"{activo.strip()};{riesgo.strip()};{impacto.strip()}"
        tratamiento = obtener_tratamiento(entrada_tratamiento)
        if isinstance(tratamiento, str) and "Error" in tratamiento:
            return jsonify({"error": tratamiento}), 500
        elif isinstance(tratamiento, dict):
            return jsonify({
                "activo": activo,
                "riesgo": riesgo,
                "impacto": impacto,
                "condicion": tratamiento.get("condicion", ""),
                "recomendacion": tratamiento.get("recomendacion", ""),
                "riesgo_adicional": tratamiento.get("riesgo", "")
            })
        else:
            return jsonify({"error": "Respuesta inesperada del modelo"}), 500
    except Exception as e:
        logging.error(f"Error en /sugerir-tratamiento: {str(e)}")
        return jsonify({"error": "Error interno del servidor"}), 500


def obtener_tratamiento(entrada_tratamiento):
    try:
        logging.info(f"Solicitando tratamiento para: {entrada_tratamiento}")
        response = client.chat.completions.create(
            model="llama2:7b",
            messages=[
                {"role": "system", "content": "Eres un experto en gestión de riesgos según ISO 27001. Responde en español. El usuario proporcionará un activo tecnológico, un riesgo y un impacto separados por ';'. Debes responder en el siguiente formato estructurado:\n\nCondición: [Situación encontrada en el activo, describe detalladamente la condición actual]\nRecomendación: [Acción correctiva o preventiva específica y detallada]\nRiesgo: Probabilidad [Baja/Media/Alta]\n\nProporciona descripciones detalladas y completas, enfocándote en medidas prácticas y efectivas."},
                {"role": "user", "content": "mi telefono movil;Acceso no autorizado;un atacante puede acceder a la información personal y confidencial almacenada en el teléfono móvil, como números de teléfono, correos electrónicos y contraseñas"},
                {"role": "assistant", "content": "Condición: Acceso no autorizado al teléfono móvil permitiendo la exposición de datos personales.\nRecomendación: Establecer un bloqueo de la pantalla de inicio que requiera autenticación con contraseña o huella digital.\nRiesgo: Probabilidad Alta"},
                {"role": "user", "content": "servidor web;Inyección SQL;un atacante puede ejecutar consultas maliciosas en la base de datos, comprometiendo la integridad de los datos"},
                {"role": "assistant", "content": "Condición: Vulnerabilidad a inyección SQL en el servidor web que permite ejecución de consultas maliciosas.\nRecomendación: Implementar validación de entradas y uso de prepared statements en consultas SQL.\nRiesgo: Probabilidad Media"},
                {"role": "user", "content": entrada_tratamiento}
            ]
        )
        answer = response.choices[0].message.content
        logging.info(f"Tratamiento generado: {answer}")

        # Parsear la respuesta para extraer Condición, Recomendación y Riesgo
        patron_condicion = r'Condición:\s*(.*?)(?=\nRecomendación:|$)'
        patron_recomendacion = r'Recomendación:\s*(.*?)(?=\nRiesgo:|$)'
        patron_riesgo = r'Riesgo:\s*Probabilidad\s*(Baja|Media|Alta)'

        match_condicion = re.search(patron_condicion, answer, re.DOTALL)
        match_recomendacion = re.search(patron_recomendacion, answer, re.DOTALL)
        match_riesgo = re.search(patron_riesgo, answer)

        if match_condicion and match_recomendacion and match_riesgo:
            condicion = match_condicion.group(1).strip()
            recomendacion = match_recomendacion.group(1).strip()
            riesgo = match_riesgo.group(1).strip()
            return {
                "condicion": condicion,
                "recomendacion": recomendacion,
                "riesgo": riesgo
            }
        else:
            logging.error(f"No se pudo parsear la respuesta: {answer}")
            return "Error al parsear la respuesta del modelo. Intente nuevamente."
    except Exception as e:
        logging.error(f"Error al obtener tratamiento: {str(e)}")
        return "Error interno al generar tratamiento. Intente nuevamente."
def obtener_riesgos(activo):
    try:
        logging.info(f"Solicitando riesgos para: {activo}")
        response = client.chat.completions.create(
            model="llama2:7b",
            messages=[
                {"role": "system", "content": "Eres un experto en gestión de riesgos según ISO 27001. Responde en español. El usuario proporcionará un activo tecnológico. Debes responder con exactamente 5 riesgos asociados, cada uno en formato: Riesgo: Descripción del impacto. Sé específico, conciso y enfócate en amenazas reales. Lista los riesgos uno por línea."},
                {"role": "user", "content": "mi raspberry pi"},
                {"role": "assistant", "content": """• **Acceso no autorizado**: terceros pueden acceder a la información almacenada o procesada en el Raspberry Pi sin permiso, lo que podría llevar a la revelación de datos confidenciales.

• **Pérdida o daño de datos**: los archivos y datos almacenados en el Raspberry Pi se pierden o dañan debido a un error en el sistema, un fallo en el hardware o una acción malintencionada.

• **Vulnerabilidades de seguridad**: El software o firmware instalados en el Raspberry Pi contienen vulnerabilidades de seguridad no detectadas y son explotados por un atacante.

• **Inseguridad de la conexión**: la conexión del Raspberry Pi a la red local o internet no esté segura y un atacante intercepta datos confidenciales o inyecta malware en el sistema.

• **Fallos hardware**: daño debido a causas como sobrecalentamiento, sobrecarga eléctrica o errores en la manufactura, lo que lleva a una pérdida de datos o inoperatividad del sistema."""},
                {"role": "user", "content": "servidor de base de datos"},
                {"role": "assistant", "content": """• **Ataques de inyección**: un atacante inyecta código malicioso en consultas, comprometiendo la integridad y confidencialidad de los datos.

• **Pérdida de disponibilidad**: fallos en el servidor o ataques DDoS impiden el acceso a la base de datos, afectando operaciones críticas.

• **Fugas de datos**: configuraciones incorrectas permiten el acceso no autorizado a información sensible almacenada.

• **Corrupción de datos**: errores en el software o hardware causan la alteración o pérdida de registros importantes.

• **Vulnerabilidades en actualizaciones**: retrasos en parches de seguridad exponen el sistema a exploits conocidos."""},
                {"role": "user", "content": activo}
            ]
        )
        answer = response.choices[0].message.content
        logging.info(f"Riesgos generados: {answer}")
        patron = r'(?:•\s*)?\*\*\s*(.+?)\*\*:\s*(.+?)\.(?=\s*\n|\s*$)'

        # Buscamos todos los patrones en la respuesta
        resultados = re.findall(patron, answer)

        # Separamos los resultados en dos listas: riesgos e impactos
        riesgos = [resultado[0] for resultado in resultados]
        impactos = [resultado[1] for resultado in resultados]

        if len(riesgos) < 5 or len(impactos) < 5:
            logging.warning("Número de riesgos/impactos menor a 5.")
            return [], []

        # Tomar los primeros 5 si hay más
        riesgos = riesgos[:5]
        impactos = impactos[:5]

        return riesgos, impactos
    except Exception as e:
        logging.error(f"Error al obtener riesgos: {str(e)}")
        return [], []

if __name__ == '__main__':
    logging.info("Iniciando aplicación Flask en host=0.0.0.0, port=5500")
    app.run(debug=True, host="0.0.0.0", port="5500")