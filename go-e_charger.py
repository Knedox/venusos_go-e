#!/usr/bin/env python
 
# import normal packages
import platform 
import logging
import sys
import os
import sys
if sys.version_info.major == 2:
    import gobject
else:
    from gi.repository import GLib as gobject
import sys
import time
import dbus
import requests # for http GET
import signal
import math 
 
# our own packages from victron
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python'))
from vedbus import VeDbusService


servicename = "com.victronenergy.evcharger"
deviceinstance = 45
api_url = "http://192.168.178.121/api/"
productname = "go-e Charger"
pv_control_enabled = 1 # startup value

def updateParameter(name, value):
    if updateParameter.store.get(name) == value: # skip if same value is already set
        return
        
    updateParameter.store.update({name:value})
    
    print ("param update", name, value)
    try:
        requests.get(api_url + "set?" + name + "=" + str(value))
    except:
        return False
    return True

updateParameter.store = {}


def requestStatus():
    return requests.get(api_url + "status").json()


def handlechangedvalue(path, value):
    global pv_control_enabled
    print("someone else updated %s to %s" % (path, value))

    if path == '/SetCurrent':
        updateParameter('amp', value)
    elif path == '/StartStop':
        if value == 0: # off -> force off
            updateParameter('frc', 1)
        else: # else be neutral
            updateParameter('frc', 0)
    elif path == '/MaxCurrent':
        updateParameter('ama', min(value,16))
    elif path == '/Mode':
        pv_control_enabled = value
        if pv_control_enabled: #auto
            print("auto")
        else: # manual
            print("manual")
            # reset values that pv might change
            #updateParameter('psm', 2) # force triple phase
            #updateParameter('amp', 16) # set back to 16A

    loop.next = 10 # wait 1 sec for go-e to process
    return True

    
    
    
def dbus_set_value(service, object_path, value):
    return dbus.SystemBus().get_object(service, object_path).SetValue(wrap_dbus_value(value))
    
def dbus_get_value(service, object_path):
    return dbus.SystemBus().get_object(service, object_path).GetValue()


def get_available_power() : 
    try:
        return -(dbus_get_value("com.victronenergy.system", "/Ac/Grid/L1/Power")\
        + dbus_get_value("com.victronenergy.system", "/Ac/Grid/L2/Power")\
        + dbus_get_value("com.victronenergy.system", "/Ac/Grid/L3/Power"))
    except:
        return 0

def set_charging_power(target_charge_power):      
    target_amps = math.floor(target_charge_power/230)
    print("target amps:", target_amps)
    if target_amps < 6:
        updateParameter('frc', 1) # force off
    else:
        updateParameter('frc', 0) # neutral on
        updateParameter('psm', 1) # force single phase
        updateParameter('amp', target_amps)
    
def loop() :
    if loop.next > 0:
        loop.next -= 1
        return True
        
    loop.next = 50 # default every 5 sec
    
    try:
        #get data from go-eCharger
        data = requestStatus()

        #send data to DBus
        _dbusservice['/FirmwareVersion'] = int(data['fwv'].replace('.', ''))
        _dbusservice['/HardwareVersion'] = 2
        _dbusservice['/Serial'] = data['fna']
      
        
        _dbusservice['/Ac/L1/Power'] = data['nrg'][7] 
        _dbusservice['/Ac/L2/Power'] = data['nrg'][8] 
        _dbusservice['/Ac/L3/Power'] = data['nrg'][9] 
        _dbusservice['/Ac/Power'] = data['nrg'][11]
        _dbusservice['/Ac/Voltage'] = data['nrg'][0]
        _dbusservice['/Current'] = max(data['nrg'][4], data['nrg'][5], data['nrg'][6])
        _dbusservice['/Ac/Energy/Forward'] = float(data['wh']) / 1000.0

        _dbusservice['/StartStop'] = int(data['alw'])
        _dbusservice['/SetCurrent'] = int(data['amp'])
        _dbusservice['/MaxCurrent'] = int(data['ama']) 
        
        if data['cdi'] != None:
            if data['cdi']['type'] == 1:
                _dbusservice['/ChargingTime'] = data['cdi']['value']/ 1000 # in seconds
            elif data['cdi']['type'] == 0:
                _dbusservice['/ChargingTime'] = (data['rbt'] - data['lcctc'])/ 1000 
            else:
                _dbusservice['/ChargingTime'] = 0
        
        _dbusservice['/MCU/Temperature'] = int(data['tma'][0])

        # venusos 0:EVdisconnected; 1:Connected; 2:Charging; 3:Charged; 4:Wait sun; 5:Wait RFID; 6:Wait enable; 7:Low SOC; 8:Ground error; 9:Welded contacts error; defaut:Unknown;
        # go-e: value 'car' 1: charging station ready, no vehicle 2: vehicle loads 3: Waiting for vehicle 4: Charge finished, vehicle still connected
        status = 0
        if int(data['car']) == 1:
            status = 0
        elif int(data['car']) == 2:
            status = 2
        elif int(data['car']) == 3:
            status = 6
        elif int(data['car']) == 4:
            status = 3
        _dbusservice['/Status'] = status
        
        target_consumption = 0
        available_power = max(get_available_power() + target_consumption  + _dbusservice['/Ac/Power'], 0)
        #print("looping", available_power)
        
        if pv_control_enabled and status > 0:
            set_charging_power(available_power)
            
        if status == 0:
            loop.next = 500 # if nothing is connected, update every 50 sec
            
    except Exception as e:
       print(e)
       
    
    return True # as gobject wants it

loop.next = 0

      
  
def shutdown(a, b):
    #dbus_set_value("com.victronenergy.vebus.ttyUSB1", "/Hub4/L1/AcPowerSetpoint", 0)
    time.sleep(0.1)
    mainloop.quit()
      
signal.signal(signal.SIGINT, shutdown)
from dbus.mainloop.glib import DBusGMainLoop
# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
DBusGMainLoop(set_as_default=True)
  
#formatting 
_kwh = lambda p, v: (str(round(v, 2)) + 'kWh')
_a = lambda p, v: (str(round(v, 1)) + 'A')
_w = lambda p, v: (str(round(v, 1)) + 'W')
_v = lambda p, v: (str(round(v, 1)) + 'V')
_degC = lambda p, v: (str(v) + '°C')
_s = lambda p, v: (str(v) + 's')
_null = lambda p, v: ''

paths={
  '/Ac/Power': {'initial': 0, 'textformat': _w},
  '/Ac/L1/Power': {'initial': 0, 'textformat': _w},
  '/Ac/L2/Power': {'initial': 0, 'textformat': _w},
  '/Ac/L3/Power': {'initial': 0, 'textformat': _w},
  '/Ac/Energy/Forward': {'initial': 0, 'textformat': _kwh},
  '/ChargingTime': {'initial': 0, 'textformat': _s},
  
  '/Ac/Voltage': {'initial': 0, 'textformat': _v},
  '/Current': {'initial': 0, 'textformat': _a},
  '/SetCurrent': {'initial': 0, 'textformat': _a},
  '/MaxCurrent': {'initial': 0, 'textformat': _a},
  '/MCU/Temperature': {'initial': 0, 'textformat': _degC},
  
  '/StartStop': {'initial': 0, 'textformat': _null},
  '/Status': {'initial': 0, 'textformat': _null},
  '/Mode': {'initial': pv_control_enabled, 'textformat': _null}
}


_dbusservice = VeDbusService(servicename)

# Create the management objects, as specified in the ccgx dbus-api document
_dbusservice.add_path('/Mgmt/ProcessName', __file__)
_dbusservice.add_path('/Mgmt/ProcessVersion', 'Unkown version, and running on Python ' + platform.python_version())
_dbusservice.add_path('/Mgmt/Connection', "go-e HTTP API V2")

# Create the mandatory objects
_dbusservice.add_path('/DeviceInstance', deviceinstance)
_dbusservice.add_path('/ProductId', 0xFFFF) # 
_dbusservice.add_path('/ProductName', productname)
_dbusservice.add_path('/CustomName', productname)    
_dbusservice.add_path('/Connected', 1)
_dbusservice.add_path('/UpdateIndex', 0)

_dbusservice.add_path('/FirmwareVersion', 0)
_dbusservice.add_path('/HardwareVersion', 0)
_dbusservice.add_path('/Serial', 0)


# add path values to dbus
for path, settings in paths.items():
  _dbusservice.add_path(
    path, settings['initial'], gettextcallback=settings['textformat'], writeable=True, onchangecallback=handlechangedvalue)

gobject.timeout_add(100, loop)  

mainloop = gobject.MainLoop()
mainloop.run()            
