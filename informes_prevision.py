import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import smtplib
import os
import requests
from datetime import datetime, timedelta
from email.message import EmailMessage
from dotenv import load_dotenv

# ==========================================
# CONFIGURACIÓN 
# ==========================================
NAS_FOLDER = os.getenv("NAS_FOLDER")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD") 
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
UMBRAL_PELIGRO = 1.5  

# ==========================================
# LÓGICA DEL SCRIPT
# ==========================================
def get_wave_forecast():
    """Extrae las series temporales marinas reales mediante API (5 días, datos horarios)."""
    lat = 39.63
    lon = -0.21
    
    url = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat}&longitude={lon}&hourly=wave_height,wave_period,wave_direction&timezone=Europe%2FMadrid&forecast_days=5"
    response = requests.get(url)
    response.raise_for_status() 
    
    datos_json = response.json()
    df = pd.DataFrame(datos_json['hourly'])
    
    df['time'] = pd.to_datetime(df['time'])
    df = df.rename(columns={
        'time': 'Fecha_Hora',
        'wave_height': 'Hs (m)',
        'wave_period': 'Periodo (s)',
        'wave_direction': 'Direccion'
    })
    
    # Extraemos la fecha sin hora para facilitar agrupaciones
    df['Dia'] = df['Fecha_Hora'].dt.date
    return df

def generate_pdf(df, filepath):
    """Genera un PDF con tres gráficas apiladas y la tabla de resumen diario."""
    # 1. Preparar la tabla de resumen
    resumen = df.groupby('Dia').agg(
        Hs_Media=('Hs (m)', 'mean'),
        Hs_Max=('Hs (m)', 'max'),
        Periodo_Medio=('Periodo (s)', 'mean')
    ).reset_index()
    
    resumen['Dia'] = pd.to_datetime(resumen['Dia']).dt.strftime('%d/%m/%Y')
    resumen['Hs_Media'] = resumen['Hs_Media'].round(2)
    resumen['Hs_Max'] = resumen['Hs_Max'].round(2)
    resumen['Periodo_Medio'] = resumen['Periodo_Medio'].round(2)
    resumen.columns = ['Fecha', 'Hs Media (m)', 'Hs Máx (m)', 'Periodo Medio (s)']

    # 2. Configurar el lienzo (Grid de 4 filas: 3 gráficas, 1 tabla)
    fig = plt.figure(figsize=(10, 15))
    gs = fig.add_gridspec(4, 1, height_ratios=[1.2, 1.2, 1.2, 1], hspace=0.3)
    
    fig.suptitle(f"INFORME PREVISIÓN DE OLEAJE - 5 DÍAS\nPuerto de Sagunto (Lat: 39.63° N, Lon: -0.21° O)\nFecha de emisión: {datetime.now().strftime('%d/%m/%Y')}", 
                 fontsize=14, fontweight='bold', y=0.95)
    
    # 3. Gráfica de Altura Significativa
    ax1 = fig.add_subplot(gs[0])
    ax1.plot(df['Fecha_Hora'], df['Hs (m)'], color='#1a5f7a', linewidth=2)
    ax1.axhline(y=UMBRAL_PELIGRO, color='#d62728', linestyle='--', alpha=0.7)
    ax1.set_ylabel('Altura Sig. (m)', fontweight='bold')
    ax1.grid(True, linestyle=':', alpha=0.6)
    
    # 4. Gráfica de Periodo
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax2.plot(df['Fecha_Hora'], df['Periodo (s)'], color='#d62728', linewidth=2)
    ax2.set_ylabel('Periodo (s)', fontweight='bold')
    ax2.grid(True, linestyle=':', alpha=0.6)
    
    # 5. Gráfica de Dirección (puntos)
    ax3 = fig.add_subplot(gs[2], sharex=ax1)
    ax3.scatter(df['Fecha_Hora'], df['Direccion'], color='#2ca02c', s=15)
    ax3.set_ylabel('Dirección (°)', fontweight='bold')
    ax3.set_yticks([0, 90, 180, 270, 360])
    ax3.set_yticklabels(['N', 'E', 'S', 'O', 'N'])
    ax3.grid(True, linestyle=':', alpha=0.6)
    
    # Formato común del eje X temporal
    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m %Hh'))
    plt.setp(ax1.get_xticklabels(), visible=False)
    plt.setp(ax2.get_xticklabels(), visible=False)
    
    # 6. Tabla inferior
    ax4 = fig.add_subplot(gs[3])
    ax4.axis('tight')
    ax4.axis('off')
    tabla = ax4.table(cellText=resumen.values, colLabels=resumen.columns, loc='center', cellLoc='center')
    tabla.auto_set_font_size(False)
    tabla.set_fontsize(11)
    tabla.scale(1, 1.8)
    
    for (row, col), cell in tabla.get_celld().items():
        if row == 0:
            cell.set_text_props(weight='bold', color='white')
            cell.set_facecolor('#1a5f7a')
            
    plt.savefig(filepath, format='pdf', bbox_inches='tight')
    plt.close()

def get_email_summary(df):
    """Redacta el cuerpo del correo evaluando el peligro según el máximo de los 5 días."""
    max_hs_total = df['Hs (m)'].max()
    dias_peligro = df[df['Hs (m)'] >= UMBRAL_PELIGRO]['Dia'].unique()
    
    if len(dias_peligro) > 0:
        fechas_str = ", ".join([d.strftime("%d/%m") for d in dias_peligro])
        return (f"⚠️ AVISO: SUPERACIÓN DE UMBRAL DE OLEAJE\n\n"
                f"Se prevé que la altura significativa (Hs) alcance o supere el límite de {UMBRAL_PELIGRO}m "
                f"durante los días: {fechas_str}, con un pico máximo de {max_hs_total:.2f}m.\n\n"
                f"Revisa el PDF adjunto con el detalle horario de altura, periodo y dirección para planificar la operativa.")
    else:
        return (f"✅ CONDICIONES ÓPTIMAS\n\n"
                f"El régimen de oleaje para los próximos 5 días se mantiene por debajo del límite de {UMBRAL_PELIGRO}m (Máximo previsto: {max_hs_total:.2f}m). "
                f"Consulta el PDF adjunto para ver las gráficas y la tabla resumen.")

def main():
    try:
        df_prediccion = get_wave_forecast()
        
        date_str = datetime.now().strftime("%Y%m%d")
        os.makedirs(NAS_FOLDER, exist_ok=True)
        pdf_filename = f"Prevision_Oleaje_Sagunto_{date_str}.pdf"
        pdf_filepath = os.path.join(NAS_FOLDER, pdf_filename)
        
        generate_pdf(df_prediccion, pdf_filepath)
        print(f"PDF generado y almacenado en: {pdf_filepath}")
        
        texto_correo = get_email_summary(df_prediccion)
        
        msg = EmailMessage()
        msg['Subject'] = f'📊 Predicción de Oleaje Sagunto (5 Días) - {datetime.now().strftime("%d/%m/%Y")}'
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_RECEIVER
        msg.set_content(texto_correo)
        
        with open(pdf_filepath, 'rb') as f:
            pdf_data = f.read()
        msg.add_attachment(pdf_data, maintype='application', subtype='pdf', filename=pdf_filename)
        
        print("Conectando con el servidor de correo...")
        servidor_smtp = 'smtp.zoho.com' # Asegúrate de que termina en .eu o .com según tu cuenta
        with smtplib.SMTP_SSL(servidor_smtp, 465) as smtp:
            smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print("¡Correo enviado con éxito!")
        
    except Exception as e:
        print(f"Se produjo un error: {e}")

if __name__ == "__main__":
    main()