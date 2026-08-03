from flask import Flask, render_template_string, request, jsonify
import sqlite3
from datetime import datetime, timedelta
import os

app = Flask(__name__)
DATABASE = 'diagnosticos.db'

# ==================== FUNCIONES DE BASE DE DATOS ====================

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def obtener_resumen_estadisticas():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) as total FROM alumnos')
    total_alumnos = cursor.fetchone()['total']
    
    cursor.execute('SELECT COUNT(*) as total FROM diagnosticos')
    total_diagnosticos = cursor.fetchone()['total']
    
    hoy = datetime.now().strftime("%Y-%m-%d")
    cursor.execute('SELECT COUNT(*) as total FROM diagnosticos WHERE fecha = ?', (hoy,))
    diagnosticos_hoy = cursor.fetchone()['total']
    
    cursor.execute('''
        SELECT medicamento, COUNT(*) as cantidad 
        FROM diagnosticos 
        WHERE medicamento != '' 
        GROUP BY medicamento 
        ORDER BY cantidad DESC 
        LIMIT 5
    ''')
    medicamentos_top = cursor.fetchall()
    
    cursor.execute('''
        SELECT sintomas, COUNT(*) as cantidad 
        FROM diagnosticos 
        GROUP BY sintomas 
        ORDER BY cantidad DESC 
        LIMIT 5
    ''')
    sintomas_top = cursor.fetchall()
    
    conn.close()
    
    return {
        'total_alumnos': total_alumnos,
        'total_diagnosticos': total_diagnosticos,
        'diagnosticos_hoy': diagnosticos_hoy,
        'medicamentos_top': [dict(m) for m in medicamentos_top],
        'sintomas_top': [dict(s) for s in sintomas_top]
    }

def buscar_alumnos(criterio, valor):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = '''
        SELECT a.matricula, a.sexo, a.fecha_registro, a.ultimo_diagnostico,
               COUNT(d.id) as total_diagnosticos
        FROM alumnos a
        LEFT JOIN diagnosticos d ON a.matricula = d.matricula
        WHERE 1=1
    '''
    params = []
    
    if criterio == 'matricula':
        query += ' AND a.matricula LIKE ?'
        params.append(f'%{valor}%')
    elif criterio == 'sintoma':
        query += ' AND d.sintomas LIKE ?'
        params.append(f'%{valor}%')
    elif criterio == 'medicamento':
        query += ' AND d.medicamento LIKE ?'
        params.append(f'%{valor}%')
    elif criterio == 'sexo' and valor in ['Masculino', 'Femenino']:
        query += ' AND a.sexo = ?'
        params.append(valor)
    
    query += ' GROUP BY a.matricula ORDER BY a.fecha_registro DESC'
    
    cursor.execute(query, params)
    resultados = cursor.fetchall()
    conn.close()
    
    return [dict(r) for r in resultados]

def obtener_diagnosticos_alumno(matricula, limite=20):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT fecha, hora, sintomas, medicamento, puntaje_sintomas
        FROM diagnosticos
        WHERE matricula = ?
        ORDER BY fecha DESC, hora DESC
        LIMIT ?
    ''', (matricula, limite))
    
    diagnosticos = cursor.fetchall()
    conn.close()
    
    return [dict(d) for d in diagnosticos]

def obtener_historial_medicamentos(matricula, horas=24):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    fecha_limite = (datetime.now() - timedelta(hours=horas)).strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        SELECT medicamento, fecha, hora
        FROM historial_medicamentos
        WHERE matricula = ?
        AND datetime(fecha || ' ' || hora) > datetime(?)
        ORDER BY fecha DESC, hora DESC
    ''', (matricula, fecha_limite))
    
    resultados = cursor.fetchall()
    conn.close()
    
    return [dict(r) for r in resultados]

def obtener_alumnos_riesgo():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            hm.matricula,
            a.sexo,
            COUNT(*) as total_medicamentos,
            GROUP_CONCAT(DISTINCT hm.medicamento) as medicamentos
        FROM historial_medicamentos hm
        JOIN alumnos a ON hm.matricula = a.matricula
        WHERE datetime(hm.fecha || ' ' || hm.hora) > datetime('now', '-24 hours')
        GROUP BY hm.matricula
        HAVING COUNT(*) >= 3
        ORDER BY total_medicamentos DESC
    ''')
    
    resultados = cursor.fetchall()
    conn.close()
    
    return [dict(r) for r in resultados]

# ==================== HTML Y ESTILOS ====================

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🏥 Sistema Médico - Dispensador Universitario</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #0f0f1a 100%);
            color: #e0e0e0;
            min-height: 100vh;
        }
        .header {
            background: linear-gradient(135deg, #1a1a2e, #2d2d3f);
            padding: 20px 40px;
            border-bottom: 2px solid #667eea;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
        }
        .header h1 { color: #667eea; font-size: 24px; display: flex; align-items: center; gap: 10px; }
        .header-info { color: #aaa; font-size: 14px; }
        .header-info span { margin-left: 20px; }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: linear-gradient(135deg, #2d2d3f, #1a1a2e);
            padding: 20px;
            border-radius: 15px;
            border: 1px solid #444;
            text-align: center;
        }
        .stat-card .number { font-size: 36px; font-weight: bold; color: #667eea; }
        .stat-card .label { color: #aaa; font-size: 14px; margin-top: 5px; }
        .stat-card.alert { border-color: #f44336; }
        .stat-card.alert .number { color: #f44336; }
        .search-section {
            background: linear-gradient(135deg, #2d2d3f, #1a1a2e);
            padding: 25px;
            border-radius: 15px;
            border: 1px solid #444;
            margin-bottom: 30px;
        }
        .search-section h2 { color: #667eea; margin-bottom: 15px; font-size: 18px; }
        .search-form {
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            align-items: center;
        }
        .search-form select, .search-form input {
            padding: 12px 20px;
            border-radius: 10px;
            border: 1px solid #444;
            background: #1a1a2e;
            color: white;
            font-size: 14px;
            min-width: 150px;
        }
        .search-form select:focus, .search-form input:focus {
            outline: none;
            border-color: #667eea;
        }
        .search-form button {
            padding: 12px 30px;
            border: none;
            border-radius: 10px;
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
        }
        .search-form button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.3);
        }
        .search-form a { color: #667eea; text-decoration: none; padding: 12px; }
        .search-form a:hover { text-decoration: underline; }
        .table-container {
            background: linear-gradient(135deg, #2d2d3f, #1a1a2e);
            padding: 20px;
            border-radius: 15px;
            border: 1px solid #444;
            overflow-x: auto;
        }
        .table-container h2 { color: #667eea; margin-bottom: 15px; font-size: 18px; }
        table { width: 100%; border-collapse: collapse; }
        th {
            background: #1a1a2e;
            color: #667eea;
            padding: 12px 15px;
            text-align: left;
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        td { padding: 12px 15px; border-bottom: 1px solid #333; font-size: 14px; }
        tr:hover td { background: #2a2a3f; }
        .badge {
            display: inline-block;
            padding: 3px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
        }
        .badge-masculino { background: #2196F3; color: white; }
        .badge-femenino { background: #E91E63; color: white; }
        .badge-riesgo {
            background: #f44336;
            color: white;
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.6; }
            100% { opacity: 1; }
        }
        .btn-detail {
            padding: 5px 15px;
            border: none;
            border-radius: 5px;
            background: #667eea;
            color: white;
            cursor: pointer;
            font-size: 12px;
        }
        .btn-detail:hover { background: #764ba2; }
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.8);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }
        .modal.active { display: flex; }
        .modal-content {
            background: linear-gradient(135deg, #2d2d3f, #1a1a2e);
            padding: 30px;
            border-radius: 20px;
            border: 1px solid #667eea;
            max-width: 700px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
        }
        .modal-content h2 { color: #667eea; margin-bottom: 20px; }
        .modal-close {
            float: right;
            background: #f44336;
            color: white;
            border: none;
            padding: 8px 20px;
            border-radius: 10px;
            cursor: pointer;
        }
        .modal-close:hover { background: #d32f2f; }
        .detail-item { padding: 10px 0; border-bottom: 1px solid #333; }
        .detail-item .label { color: #888; font-size: 12px; text-transform: uppercase; }
        .detail-item .value { color: white; font-size: 16px; margin-top: 5px; }
        .no-results { text-align: center; padding: 40px; color: #666; }
        hr { border-color: #444; margin: 15px 0; }
        @media (max-width: 768px) {
            .header { flex-direction: column; text-align: center; gap: 10px; }
            .search-form { flex-direction: column; }
            .search-form select, .search-form input, .search-form button { width: 100%; }
            .stats-grid { grid-template-columns: repeat(2, 1fr); }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🏥 Sistema de Diagnóstico Médico</h1>
        <div class="header-info">
            <span>🔄 Actualizado en tiempo real</span>
            <span>📊 {{ stats.total_alumnos }} alumnos registrados</span>
        </div>
    </div>
    
    <div class="container">
        <div class="stats-grid">
            <div class="stat-card">
                <div class="number">{{ stats.total_alumnos }}</div>
                <div class="label">👤 Alumnos Registrados</div>
            </div>
            <div class="stat-card">
                <div class="number">{{ stats.total_diagnosticos }}</div>
                <div class="label">📋 Diagnósticos Totales</div>
            </div>
            <div class="stat-card">
                <div class="number">{{ stats.diagnosticos_hoy }}</div>
                <div class="label">📅 Diagnósticos Hoy</div>
            </div>
            <div class="stat-card {% if stats.alumnos_riesgo > 0 %}alert{% endif %}">
                <div class="number">{{ stats.alumnos_riesgo }}</div>
                <div class="label">⚠️ Alumnos en Riesgo</div>
            </div>
        </div>
        
        <div class="search-section">
            <h2>🔍 Buscar Alumnos</h2>
            <form class="search-form" method="GET" action="/">
                <select name="criterio">
                    <option value="matricula" {% if criterio == 'matricula' %}selected{% endif %}>Matrícula</option>
                    <option value="sintoma" {% if criterio == 'sintoma' %}selected{% endif %}>Síntoma</option>
                    <option value="medicamento" {% if criterio == 'medicamento' %}selected{% endif %}>Medicamento</option>
                    <option value="sexo" {% if criterio == 'sexo' %}selected{% endif %}>Sexo</option>
                </select>
                <input type="text" name="valor" placeholder="Buscar..." value="{{ valor or '' }}">
                <button type="submit">Buscar</button>
                {% if criterio %}
                <a href="/">Limpiar</a>
                {% endif %}
            </form>
        </div>
        
        <div class="table-container">
            <h2>📋 Listado de Alumnos</h2>
            {% if alumnos %}
            <table>
                <thead>
                    <tr>
                        <th>Matrícula</th>
                        <th>Sexo</th>
                        <th>Fecha Registro</th>
                        <th>Último Diagnóstico</th>
                        <th>Total Diagnósticos</th>
                        <th>Acciones</th>
                    </tr>
                </thead>
                <tbody>
                    {% for alumno in alumnos %}
                    <tr>
                        <td><strong>{{ alumno.matricula }}</strong></td>
                        <td><span class="badge badge-{{ alumno.sexo.lower() }}">{{ alumno.sexo }}</span></td>
                        <td>{{ alumno.fecha_registro }}</td>
                        <td>{{ alumno.ultimo_diagnostico or 'Sin diagnóstico' }}</td>
                        <td>{{ alumno.total_diagnosticos }}</td>
                        <td>
                            <button class="btn-detail" onclick="verDetalle('{{ alumno.matricula }}')">Ver Detalle</button>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <div class="no-results">
                <p>🔍 No se encontraron resultados</p>
                <p style="color: #888; font-size: 14px;">Prueba con otro criterio de búsqueda</p>
            </div>
            {% endif %}
        </div>
    </div>
    
    <div class="modal" id="modalDetalle">
        <div class="modal-content">
            <button class="modal-close" onclick="cerrarModal()">✕ Cerrar</button>
            <h2 id="modalTitle">Detalle del Alumno</h2>
            <div id="modalBody"></div>
        </div>
    </div>
    
    <script>
        function verDetalle(matricula) {
            fetch(`/alumno/${matricula}`)
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        document.getElementById('modalBody').innerHTML = `<p>Error: ${data.error}</p>`;
                    } else {
                        let html = `
                            <div class="detail-item"><div class="label">Matrícula</div><div class="value"><strong>${data.alumno.matricula}</strong></div></div>
                            <div class="detail-item"><div class="label">Sexo</div><div class="value"><span class="badge badge-${data.alumno.sexo.toLowerCase()}">${data.alumno.sexo}</span></div></div>
                            <div class="detail-item"><div class="label">Fecha de Registro</div><div class="value">${data.alumno.fecha_registro}</div></div>
                            <div class="detail-item"><div class="label">Último Diagnóstico</div><div class="value">${data.alumno.ultimo_diagnostico || 'Sin diagnóstico'}</div></div>
                            <hr><h3 style="color: #667eea; margin-bottom: 10px;">📋 Historial de Diagnósticos</h3>
                        `;
                        if (data.diagnosticos && data.diagnosticos.length > 0) {
                            data.diagnosticos.forEach(d => {
                                html += `<div class="detail-item"><div class="label">${d.fecha} ${d.hora}</div><div class="value">${d.sintomas}</div><div style="color: #888; font-size: 13px;">💊 ${d.medicamento || 'Sin medicamento'}</div></div>`;
                            });
                        } else {
                            html += `<p style="color: #888;">No hay diagnósticos registrados</p>`;
                        }
                        if (data.medicamentos && data.medicamentos.length > 0) {
                            html += `<hr><h3 style="color: #667eea; margin-bottom: 10px;">💊 Medicamentos (últimas 24h)</h3>`;
                            data.medicamentos.forEach(m => {
                                html += `<div class="detail-item"><div class="label">${m.fecha} ${m.hora}</div><div class="value">${m.medicamento}</div></div>`;
                            });
                        }
                        document.getElementById('modalBody').innerHTML = html;
                    }
                    document.getElementById('modalTitle').textContent = `Detalle - ${matricula}`;
                    document.getElementById('modalDetalle').classList.add('active');
                })
                .catch(error => {
                    document.getElementById('modalBody').innerHTML = `<p>Error al cargar los datos</p>`;
                });
        }
        function cerrarModal() {
            document.getElementById('modalDetalle').classList.remove('active');
        }
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') cerrarModal();
        });
        document.getElementById('modalDetalle').addEventListener('click', function(e) {
            if (e.target === this) cerrarModal();
        });
    </script>
</body>
</html>
'''

# ==================== RUTAS FLASK ====================

@app.route('/')
def index():
    criterio = request.args.get('criterio', '')
    valor = request.args.get('valor', '')
    
    stats = obtener_resumen_estadisticas()
    alumnos_riesgo = obtener_alumnos_riesgo()
    stats['alumnos_riesgo'] = len(alumnos_riesgo)
    
    if criterio and valor:
        alumnos = buscar_alumnos(criterio, valor)
    else:
        alumnos = buscar_alumnos('matricula', '')
    
    return render_template_string(
        HTML_TEMPLATE,
        stats=stats,
        alumnos=alumnos,
        criterio=criterio,
        valor=valor
    )

@app.route('/alumno/<matricula>')
def detalle_alumno(matricula):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM alumnos WHERE matricula = ?', (matricula,))
    alumno = cursor.fetchone()
    
    if not alumno:
        conn.close()
        return jsonify({'error': 'Alumno no encontrado'}), 404
    
    diagnosticos = obtener_diagnosticos_alumno(matricula, 20)
    medicamentos = obtener_historial_medicamentos(matricula, 24)
    
    conn.close()
    
    return jsonify({
        'alumno': dict(alumno),
        'diagnosticos': diagnosticos,
        'medicamentos': medicamentos
    })

@app.route('/api/estadisticas')
def api_estadisticas():
    stats = obtener_resumen_estadisticas()
    alumnos_riesgo = obtener_alumnos_riesgo()
    stats['alumnos_riesgo'] = len(alumnos_riesgo)
    return jsonify(stats)

@app.route('/api/alumnos/riesgo')
def api_alumnos_riesgo():
    alumnos = obtener_alumnos_riesgo()
    return jsonify(alumnos)

# ==================== INICIO DEL SERVIDOR ====================

if __name__ == '__main__':

        # ==================== API PARA LA PANTALLA ESP32 ====================

    def inicializar_inventario():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
        
            CREATE TABLE IF NOT EXISTS inventario (
                tubo INTEGER PRIMARY KEY,
                medicamento TEXT,
                cantidad INTEGER
            )
        ''')
        # Llenar inventario a 7 pastillas si está vacío
        cursor.execute('SELECT COUNT(*) as count FROM inventario')
        if cursor.fetchone()['count'] == 0:
            meds = [(1, 'PARACETAMOL', 7), (2, 'IBUPROFENO', 7), (3, 'HIOSCINA IBUPROFENO', 7), 
                    (4, 'ANTIHISTAMÍNICO', 7), (5, 'ANTIÁCIDO', 7)]
            cursor.executemany('INSERT INTO inventario VALUES (?, ?, ?)', meds)
        conn.commit()
        conn.close()

    # Ejecutamos la función al arrancar el servidor
    inicializar_inventario()

    @app.route('/api/login', methods=['POST'])
    def api_login():
        data = request.json
        matricula = data.get('matricula')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Validar el bloqueo de 8 horas (La memoria es eterna aquí)
        cursor.execute('''
            SELECT fecha, hora FROM historial_medicamentos 
            WHERE matricula = ? 
            ORDER BY fecha DESC, hora DESC LIMIT 1
        ''', (matricula,))
        ultimo = cursor.fetchone()
        
        if ultimo:
            ultima_fecha = datetime.strptime(f"{ultimo['fecha']} {ultimo['hora']}", "%Y-%m-%d %H:%M:%S")
            tiempo_pasado = datetime.now() - ultima_fecha
            if tiempo_pasado < timedelta(hours=8):
                horas_restantes = 8 - int(tiempo_pasado.total_seconds() // 3600)
                conn.close()
                return jsonify({"autorizado": False, "mensaje": f"Ya recibiste medicamento. Espera {horas_restantes} horas."})
                
        # 2. Verificar si el usuario ya usó el sistema antes (para omitir pregunta de sexo)
        cursor.execute('SELECT sexo FROM alumnos WHERE matricula = ?', (matricula,))
        alumno = cursor.fetchone()
        conn.close()
        
        if alumno:
            return jsonify({"autorizado": True, "sexo": alumno['sexo'], "es_nuevo": False})
        else:
            return jsonify({"autorizado": True, "sexo": "", "es_nuevo": True})

    @app.route('/api/diagnostico', methods=['POST'])
    def api_diagnostico():
        data = request.json
        matricula = data.get('matricula')
        sexo = data.get('sexo')
        sintomas = data.get('sintomas')
        medicamento = data.get('medicamento')
        temp = data.get('temperatura')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        fecha = datetime.now().strftime("%Y-%m-%d")
        hora = datetime.now().strftime("%H:%M:%S")
        
        # Registrar al usuario si era la primera vez
        cursor.execute('INSERT OR IGNORE INTO alumnos (matricula, sexo, fecha_registro) VALUES (?, ?, ?)', 
                    (matricula, sexo, f"{fecha} {hora}"))
        
        # Guardar diagnóstico incluyendo la temperatura del sensor
        sintomas_final = f"{sintomas} (Temp: {temp}°C)"
        cursor.execute('INSERT INTO diagnosticos (matricula, fecha, hora, sintomas, medicamento) VALUES (?, ?, ?, ?, ?)',
                    (matricula, fecha, hora, sintomas_final, medicamento))
                    
        if medicamento:
            # Registrar en el historial para activar el bloqueo de 8 horas
            cursor.execute('INSERT INTO historial_medicamentos (matricula, medicamento, fecha, hora) VALUES (?, ?, ?, ?)',
                        (matricula, medicamento, fecha, hora))
                        
            # Restar del inventario y alertar en consola si quedan 2 o menos
            cursor.execute('UPDATE inventario SET cantidad = cantidad - 1 WHERE medicamento = ? AND cantidad > 0', (medicamento,))
            cursor.execute('SELECT tubo, cantidad FROM inventario WHERE medicamento = ?', (medicamento,))
            inv = cursor.fetchone()
            if inv and inv['cantidad'] <= 2:
                print(f"\n{'='*60}\n⚠️ AVISO: Quedan {inv['cantidad']} pastillas de {medicamento}. Reponer en tubo {inv['tubo']}.\n{'='*60}\n")
                
        conn.commit()
        conn.close()
        return jsonify({"exito": True})

    print("=" * 60)
    print("🏥 SERVIDOR MÉDICO - DISPENSADOR UNIVERSITARIO")
    print("=" * 60)
    print(f"📂 Base de datos: {DATABASE}")
    print("🌐 Servidor iniciado en: http://localhost:5000")
    print("📊 Acceso para personal médico")
    print("=" * 60)
    print("⚠️  Presiona Ctrl+C para detener el servidor")
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=5000)