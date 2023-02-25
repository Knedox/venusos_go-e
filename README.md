# VenusOS driver for go-e charging station to control the charging process based on PV input

# Installation
1. Download the *go-e_charger.py* file and put it into any folder on the venus device e.g. to */home/root*
2. Modify the api_url in the script to fit your charger
3. Enable http v2 api on the charger using the app
4. Add *python /home/root/go-e_charger.py &* to your */data/rc.local* for autostart

# How it works
The script periodically polls the go-e chargers API and pushes the received data to dbus every ~50 sec.

In case a car is connected this interval is reduced to 5 sec.

There exist two modes:
- Automatic: PV driven mode, current is controlled based on currently available power
- Manual: All settings can be controlled manually via venusOS website

Limitations:
only single phase mode supported at the moment
# Screenshots

![image](/doc/control_menu.JPG)
![image](/doc/view.JPG)
