import speech_recognition as sr
import os
import sys
import google.generativeai as genai
import subprocess
import json
import platform
from gtts import gTTS
import uuid
import re
import time
import difflib
import pygame
import threading
import urllib.parse

# --- AYARLAR ---
GEMINI_API_KEY = "AIzaSyATsBYWQ051Mnen7lMFr6sDIEUahcnQ2FE"
genai.configure(api_key=GEMINI_API_KEY)

generation_config = {
    "response_mime_type": "application/json",
}
action_model = genai.GenerativeModel('gemini-1.5-flash', generation_config=generation_config)
chat_model = genai.GenerativeModel('gemini-1.5-flash')

pygame.init()
pygame.mixer.init()

KOMUTLAR_DOSYASI = "ogrenilmis_eylemler.json"

konusma_aktif = True
r = sr.Recognizer()
r.pause_threshold = 2.0

def eylemleri_yukle():
    try:
        with open(KOMUTLAR_DOSYASI, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def eylem_kaydet(sesli_istek, eylem_detaylari):
    ogrenilmis_eylemler = eylemleri_yukle()
    ogrenilmis_eylemler[sesli_istek] = eylem_detaylari
    with open(KOMUTLAR_DOSYASI, 'w', encoding='utf-8') as f:
        json.dump(ogrenilmis_eylemler, f, indent=4, ensure_ascii=False)
    print(f"'{sesli_istek}' isteği '{eylem_detaylari['eylem']}' olarak öğrenildi.")

def find_best_match(user_command, commands):
    best_match = None
    highest_score = 0.8
    if not user_command: return None
    for cmd_key in commands.keys():
        score = difflib.SequenceMatcher(None, user_command, cmd_key).ratio()
        if score > highest_score:
            highest_score = score
            best_match = cmd_key
    return best_match

def ping_ozet(adres):
    try:
        print(f"Pinge başlandı: {adres}")
        if platform.system() == "Windows":
            ping_cmd = ["ping", "-n", "4", adres]
        else:
            ping_cmd = ["ping", "-c", "4", adres]
        sonuc = subprocess.run(ping_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        cikti = sonuc.stdout + sonuc.stderr
        # Basit özet
        kayip = re.search(r"(\d+)%.*kayb", cikti) or re.search(r"(\d+)% loss", cikti)
        ort = re.search(r"Average = (\d+)", cikti) or re.search(r"avg(?:/|=)([\d.]+)", cikti)
        if kayip:
            kayip_orani = kayip.group(1)
        else:
            kayip_orani = "?"
        if ort:
            ortalama = ort.group(1)
        else:
            ortalama = "?"
        ozet = f"Ping sonucu: kayıp oranı %{kayip_orani}, ortalama süre {ortalama} ms."
        return ozet
    except Exception as e:
        return f"Ping sırasında hata oluştu: {e}"

def eylem_yonlendirici(eylem_detaylari, asistan_hafizasi):
    eylem = eylem_detaylari.get("eylem")
    parametreler = eylem_detaylari.get("parametreler", {})

    if eylem == "ping_at":
        adres = parametreler.get("adres")
        if not adres:
            return False, "Ping atmak için bir adres yok."
        ozet = ping_ozet(adres)
        return True, ozet
    # Diğer klasik eylemler buraya eklenebilir (örneğin web_arama, klasor_olustur...)
    else:
        return False, "Bu eylemi henüz yapamıyorum."

def sesli_yanit(text, asistan_hafizasi):
    asistan_hafizasi['son_sesli_yanit'] = text
    def play_and_delete(filename):
        try:
            pygame.mixer.music.load(filename)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
            pygame.mixer.music.unload()
            time.sleep(0.2)
            os.remove(filename)
        except Exception as e:
            print(f"Hata (play_and_delete): {e}")
    if not text or not konusma_aktif: return None
    print(f"Sesli Yanıt: {text}")
    try:
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
        tts = gTTS(text=text, lang='tr')
        filename = f"temp_{uuid.uuid4()}.mp3"
        tts.save(filename)
        playback_thread = threading.Thread(target=play_and_delete, args=(filename,), daemon=True)
        playback_thread.start()
        return playback_thread
    except Exception as e:
        print(f"Sesli yanıt sırasında bir hata oluştu: {e}")
        return None

def ana_dongu():
    global konusma_aktif
    ogrenilmis_eylemler = eylemleri_yukle()
    asistan_hafizasi = {}
    ogren_modu = False
    yeni_komut = None

    try:
        mic_list = sr.Microphone.list_microphone_names()
        if not mic_list:
            print("Hiç mikrofon bulunamadı! Program sonlandırılıyor.")
            return
        mic_index = 0
    except Exception as e:
        print(f"KRİTİK HATA: Mikrofonlar listelenemedi: {e}")
        return

    try:
        with sr.Microphone(device_index=mic_index) as source:
            print("\n--- Akıllı Sesli Asistan (Nihai Sürüm) ---")
            playback_thread = sesli_yanit("Asistan hazır.", asistan_hafizasi)
            if playback_thread: playback_thread.join()
            while True:
                print("\nDinliyorum...")
                try:
                    r.adjust_for_ambient_noise(source, duration=0.5)
                    audio = r.listen(source)
                    text = r.recognize_google(audio, language="tr-TR").lower()
                    print(f"Anlaşılan: '{text}'")

                    if ogren_modu:
                        if not yeni_komut:
                            # 1. adım: Öğrenilecek komutı al
                            yeni_komut = text
                            playback_thread = sesli_yanit(f"'{text}' için hangi aksiyonu yapmalıyım? Örneğin: 192.168.1.1'e ping at.", asistan_hafizasi)
                            if playback_thread: playback_thread.join()
                            continue
                        else:
                            # 2. adım: Aksiyon bilgisini al ve kaydet
                            aksiyon_cumlesi = text
                            # Eğer cümle 'X ping at' şeklindeyse otomatik algıla
                            ping_match = re.match(r"([\d\.]+)'?e? ping at", aksiyon_cumlesi)
                            if ping_match:
                                adres = ping_match.group(1)
                                yeni_eylem = {"eylem": "ping_at", "parametreler": {"adres": adres}}
                                eylem_kaydet(yeni_komut, yeni_eylem)
                                playback_thread = sesli_yanit(f"'{yeni_komut}' komutunu '{adres}' adresine ping atacak şekilde kaydettim.", asistan_hafizasi)
                            else:
                                playback_thread = sesli_yanit("Şu an sadece ping atma eylemlerini otomatik olarak öğrenebiliyorum.", asistan_hafizasi)
                            ogren_modu = False
                            yeni_komut = None
                            if playback_thread: playback_thread.join()
                            continue

                    if text == "çıkış":
                        playback_thread = sesli_yanit("Görüşmek üzere.", asistan_hafizasi)
                        if playback_thread: playback_thread.join()
                        break
                    elif text == "sus":
                        konusma_aktif = False
                        continue
                    elif text == "konuş":
                        konusma_aktif = True
                        playback_thread = sesli_yanit("Tekrar konuşuyorum.", asistan_hafizasi)
                        if playback_thread: playback_thread.join()
                        continue
                    elif text == "öğren":
                        ogren_modu = True
                        yeni_komut = None
                        playback_thread = sesli_yanit("Ne öğreneyim?", asistan_hafizasi)
                        if playback_thread: playback_thread.join()
                        continue

                    matched_command = find_best_match(text, ogrenilmis_eylemler)
                    if matched_command:
                        eylem_detaylari = ogrenilmis_eylemler[matched_command]
                        basarili, mesaj = eylem_yonlendirici(eylem_detaylari, asistan_hafizasi)
                        playback_thread = sesli_yanit(mesaj, asistan_hafizasi)
                        if playback_thread: playback_thread.join()
                        continue

                    # Diğer klasik asistan cevapları
                    context_prompt = (f"Sen, bir Türk kullanıcının bilgisayarında çalışan kişisel bir sesli asistansın. "
                                      f"Sana sorulan sorulara her zaman Türkçe, kısa, doğrudan ve sohbet havasında yanıt ver. "
                                      f"Liste veya madde imleri kullanmaktan kaçın. "
                                      f"Kullanıcının sorusu şu: '{text}'")
                    sohbet_yaniti = chat_model.generate_content(context_prompt)
                    playback_thread = sesli_yanit(sohbet_yaniti.text, asistan_hafizasi)
                    if playback_thread: playback_thread.join()

                except sr.UnknownValueError:
                    print("Anlayamadım.")
                except sr.RequestError as e:
                    print(f"Servis hatası; {e}")
                except KeyboardInterrupt:
                    sesli_yanit("Hoşça kalın.", asistan_hafizasi)
                    break
    except Exception as e:
        print(f"\nKRİTİK HATA: Mikrofon başlatılamadı - {e}")

if __name__ == "__main__":
    ana_dongu()
