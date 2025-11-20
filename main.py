# main.py
import uasyncio as asyncio
from machine import Pin, PWM
import network
import server

# --- CONFIGURATION ---
SSID = "your SSID"   #replace this line with your wifi ssid
PASSWORD = "your password" #replace this line with your wifi password
# ---------------------

class LEDController:
    def __init__(self, pin):
        self.pwm = PWM(Pin(pin), freq=1000)
        self.pwm.duty(0)
        self.mode = 'BOOT'
        
    async def run(self):
        sta = network.WLAN(network.STA_IF)
        ap = network.WLAN(network.AP_IF)
        
        while True:
            if sta.isconnected(): self.mode = 'CONNECTED'
            elif ap.active(): self.mode = 'AP'
            else: self.mode = 'CONNECTING'

            if self.mode == 'CONNECTING':
                self.pwm.duty(1023); await asyncio.sleep_ms(100)
                self.pwm.duty(0); await asyncio.sleep_ms(100)
            elif self.mode == 'AP':
                for i in range(0, 1024, 40): self.pwm.duty(i); await asyncio.sleep_ms(20)
                for i in range(1023, -1, -40): self.pwm.duty(i); await asyncio.sleep_ms(20)
            elif self.mode == 'CONNECTED':
                self.pwm.duty(1023); await asyncio.sleep_ms(2800)
                self.pwm.duty(0); await asyncio.sleep_ms(200)

async def connection_manager():
    sta = network.WLAN(network.STA_IF)
    ap = network.WLAN(network.AP_IF)
    print("Connecting to WiFi...")
    sta.active(True)
    sta.connect(SSID, PASSWORD)
    
    for _ in range(100):
        if sta.isconnected():
            print("Connected!", sta.ifconfig()[0])
            return 
        await asyncio.sleep_ms(100) 
        
    print("WiFi Failed. Starting Hotspot...")
    sta.active(False)
    ap.active(True)
    ap.config(essid='ESP32-offline', password='password123')
    print("Hotspot active:", ap.ifconfig()[0])

async def main():
    try:
        import webrepl
        webrepl.start(password="1234")
    except: pass
    
    led = LEDController(2)
    asyncio.create_task(led.run())
    await connection_manager()
    
    print("Starting Server...")
    await server.start_server()
    
    while True: await asyncio.sleep(10)

try:
    asyncio.run(main())
finally:
    asyncio.new_event_loop()
