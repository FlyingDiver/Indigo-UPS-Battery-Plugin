#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# Copyright (c) 2011, Benjamin Schollnick. All rights reserved.
# http://www.schollnick.net/Wordpress

################################################################################
import subprocess
import time

################################################################################
# Globals
################################################################################

current_device_version = 4

################################################################################
class Plugin(indigo.PluginBase):
    ########################################
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        """
        Initialization of Battery Monitor
        """
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        self.debug = pluginPrefs.get("showDebugInfo", False)
        #
        # Perform a version check on the Find My iDevices plugin itself
        #
        # self.VersionCheck ()
        self.monitors = []
        self.verify_preference("Timing", 5)
        self.verify_preference("PowerFailureTiming", 1)
        self.verify_preference("SupressLogging", True)

    ########################################
    def __del__(self):
        indigo.PluginBase.__del__(self)

    ########################################
    # Built-in control methods
    ########################################
    def startup(self):
        """
        Startup and initialization code
        """
        #
        # Load settings from Indigo Database
        #
        self.debug = self.pluginPrefs.get("showDebugInfo", False)
        self.debugLog("Debug Mode is On (Only recommended for Testing Purposes)")

    ########################################
    def verify_preference(self, preference_key, default_value):
        if preference_key in self.pluginPrefs:
            return
        else:
            self.pluginPrefs[preference_key] = default_value

    @staticmethod
    def verify_device_properties(dev, property_name, boolean=False, default_value=""):
        newProps = dev.pluginProps  # dev.globalProps[plugin_id]
        if property_name in newProps:
            return
        else:
            if boolean:
                newProps[property_name] = True
            else:
                newProps[property_name] = default_value

            dev.replacePluginPropsOnServer(newProps)

    @staticmethod
    def update_device_property(dev, property_name, new_value):
        newProps = dev.pluginProps
        newProps.update({property_name: new_value})
        dev.replacePluginPropsOnServer(newProps)
        return None

    ########################################

    def deviceStartComm(self, dev):
        self.verify_device_properties(dev, "device_version", boolean=False, default_value="000")
        self.verify_device_properties(dev, "Model", boolean=False, default_value="")
        self.verify_device_properties(dev, "ACPower", boolean=True)
        self.verify_device_properties(dev, "PowerSource", boolean=False, default_value="")

        dv = int(dev.pluginProps["device_version"])
        if current_device_version != dv:
            dev.stateListOrDisplayStateIdChanged()
            self.update_device_property(dev, "device_version", new_value=current_device_version)

        if dev.deviceTypeId == "BatteryMonitor":
            self.monitors.append(dev.id)
            if len(self.monitors) >= 2:
                self.errorLog("Only One Battery & UPS Monitor can be used.")
                self.monitors = self.monitors[0]

    def deviceStopComm(self, dev):
        if dev.deviceTypeId == "BatteryMonitor":
            self.monitors.remove(dev.id)

    @staticmethod
    def get_battery_status():
        proc = subprocess.Popen(['pmset', '-g', 'batt'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = proc.communicate()
        out = out.decode('utf8').split("\n")

        if len(out) == 2:
            return "AC Power - No Battery", "No Battery or UPS", False, 0, 0, 0, 0

        power_status = out[0].split("'")[1]
        data = out[1].split("\t")
        ups_model = data[0]
        data = data[1].split(";")
        percentage = data[0][0:-1]  # data[1][0:percent_locale]
        charging = data[1].find("discharging") == -1
        if not charging:
            ctime = data[2][0:data[2].find(":") + 3].strip()
            c_hours = data[2][0:ctime.find(":") + 1]
            c_min = data[2][ctime.find(":") + 2:ctime.find(":") + 4]
        else:
            ctime = 0
            c_hours = 0
            c_min = 0

        return power_status, ups_model, charging, percentage, ctime, c_hours, c_min

    def runConcurrentThread(self):
        try:
            while True:
                power_status, ups_model, charging, percentage, timestring, hours, c_min = self.get_battery_status()
                if self.pluginPrefs["SupressLogging"] and charging:
                    pass
                else:
                    indigo.server.log(f"\tPower Status    - {power_status}")
                    indigo.server.log(f"\tUPS Model       - {ups_model}")
                    indigo.server.log(f"\tCharging Status - {charging}")
                    indigo.server.log(f"\tBattery Charge  - {percentage:>02}")
                    if charging:
                        indigo.server.log(f"Refreshing in {self.pluginPrefs['Timing']} Minutes")
                    else:
                        indigo.server.log(f"Refreshing in {self.pluginPrefs['PowerFailureTiming']} Minutes")

                if self.monitors == {}:
                    indigo.server.log("\tNo Battery & UPS Monitor device defined.")
                else:
                    if len(self.monitors) >= 1:
                        BatteryMonitor = indigo.devices[self.monitors[0]]
                        if BatteryMonitor.states["Model"] != ups_model:
                            BatteryMonitor.updateStateOnServer("Model", ups_model)

                        if BatteryMonitor.states["ACPower"] != power_status:
                            BatteryMonitor.updateStateOnServer("ACPower", power_status)

                        if BatteryMonitor.states["Charging"] != charging:
                            BatteryMonitor.updateStateOnServer("Charging", charging)

                        if BatteryMonitor.states["BatteryLevel"] != percentage:
                            BatteryMonitor.updateStateOnServer("BatteryLevel", percentage)

                        if BatteryMonitor.states["BatteryTimeRemaining"] != int(hours) * 60 + int(c_min):
                            BatteryMonitor.updateStateOnServer("BatteryTimeRemaining", int(hours) * 60 + int(c_min))

                        if BatteryMonitor.states["PowerSource"] != power_status:
                            BatteryMonitor.updateStateOnServer("PowerSource", power_status)

                        BatteryMonitor.updateStateOnServer("TimeDateStamp", time.ctime())

                if charging:
                    self.sleep(int(self.pluginPrefs["Timing"]) * 60)
                else:
                    self.sleep(int(self.pluginPrefs["PowerFailureTiming"]) * 60)

        except self.StopThread:
            indigo.server.log("Stopping Plugin")
