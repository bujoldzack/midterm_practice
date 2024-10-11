#!/usr/bin/env python
import os
import time
import json
import threading
import ADC0832
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
import RPi.GPIO as GPIO
import config

latest_temperature = None
latest_volume = None

LED_PIN = 5
GPIO.setmode(GPIO.BCM)
GPIO.setup(LED_PIN, GPIO.OUT)

def init_adc():
    ADC0832.setup()
    GPIO.output(LED_PIN, GPIO.LOW)

def readSensor(id):
    tfile = open("/sys/bus/w1/devices/" + id + "/w1_slave")
    text = tfile.read()
    tfile.close()
    secondline = text.split("\n")[1]
    temperaturedata = secondline.split(" ")[9]
    temperature = float(temperaturedata[2:]) / 1000
    print("Sensor: " + id + " - Current temperature : %0.3f C" % temperature)
    return temperature

def readSensors():
    global latest_temperature
    for file in os.listdir("/sys/bus/w1/devices/"):
        if file.startswith("28-"):
            latest_temperature = readSensor(file)
            return
    print("No sensor found! Check connection")

def loop_temperature():
    while True:
        readSensors()
        time.sleep(5)

def loop_microphone():
    global latest_volume
    while True:
        res = ADC0832.getResult()
        latest_volume = 255 - res
        print('Analog value: %03d  Volume: %d' % (res, latest_volume))
        time.sleep(5)

def publish_data(myMQTTClient):
    while True:
        if latest_temperature is not None and latest_volume is not None:
            payload = json.dumps({
                "temperature": latest_temperature,
                "volume": latest_volume
            })
            myMQTTClient.publish(config.TOPIC, payload, 1)
            print("Published: " + payload)
        time.sleep(5)

def republish_callback(client, userdata, message):
    print("Received message from republish topic: ", message.payload.decode('utf-8'))
    
    try:
        data = json.loads(message.payload)
        temperature = data.get('temperature', None)
        
        if temperature is not None:
            if temperature > 25:
                print("Temperature over 25°C, turning on LED")
                GPIO.output(LED_PIN, GPIO.HIGH)
            else:
                print("Temperature below 25°C, turning off LED")
                GPIO.output(LED_PIN, GPIO.LOW)
    
    except Exception as e:
        print(f"Error processing message: {e}")

if __name__ == '__main__':
    myMQTTClient = AWSIoTMQTTClient(config.CLIENT_ID)
    myMQTTClient.configureEndpoint(config.AWS_HOST, config.AWS_PORT)
    myMQTTClient.configureCredentials(config.AWS_ROOT_CA, config.AWS_PRIVATE_KEY, config.AWS_CLIENT_CERT)
    myMQTTClient.configureConnectDisconnectTimeout(config.CONN_DISCONN_TIMEOUT)
    myMQTTClient.configureMQTTOperationTimeout(config.MQTT_OPER_TIMEOUT)

    if myMQTTClient.connect():
        print('AWS connection succeeded')

    myMQTTClient.subscribe("champlain/republish", 1, republish_callback)
    
    init_adc()

    try:
        temp_thread = threading.Thread(target=loop_temperature)
        mic_thread = threading.Thread(target=loop_microphone)
        pub_thread = threading.Thread(target=publish_data, args=(myMQTTClient,))
        
        temp_thread.start()
        mic_thread.start()
        pub_thread.start()
        
        temp_thread.join()
        mic_thread.join()
        pub_thread.join()
    except KeyboardInterrupt:
        ADC0832.destroy()
        GPIO.cleanup() 
        print('The end!')

