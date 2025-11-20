# boot.py
import network
# Turn on WiFi interface but don't wait (Main handles it)
sta_if = network.WLAN(network.STA_IF)
sta_if.active(True)
