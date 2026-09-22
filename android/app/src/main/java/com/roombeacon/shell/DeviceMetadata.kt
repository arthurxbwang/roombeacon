package com.roombeacon.shell

import android.annotation.SuppressLint
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import org.json.JSONArray
import org.json.JSONObject
import java.net.NetworkInterface
import java.net.SocketException

object DeviceMetadata {
    @SuppressLint("MissingPermission", "HardwareIds")
    fun collect(context: Context): JSONObject {
        val connectivity = context.getSystemService(ConnectivityManager::class.java)
        val capabilities = connectivity.getNetworkCapabilities(connectivity.activeNetwork)
        val network = when {
            capabilities == null -> "offline"
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "ethernet"
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "wifi"
            else -> "other"
        }
        val serial = try { Build.getSerial().takeUnless { it == Build.UNKNOWN } ?: "" }
            catch (_: SecurityException) { "" }
        val manager = context.getSystemService(DevicePolicyManager::class.java)
        val factoryMac = if (manager.isDeviceOwnerApp(context.packageName)) {
            try { manager.getWifiMacAddress(ComponentName(context, KioskAdminReceiver::class.java)) ?: "" }
            catch (_: SecurityException) { "" }
        } else ""
        val interfaces = JSONArray()
        try {
            NetworkInterface.getNetworkInterfaces()?.toList()?.filter { !it.isLoopback }?.take(12)?.forEach { nic ->
                val mac = try { nic.hardwareAddress?.joinToString(":") { "%02X".format(it.toInt() and 255) } ?: "" }
                    catch (_: SocketException) { "" }
                val addresses = nic.inetAddresses.toList().filter { !it.isLoopbackAddress && !it.isLinkLocalAddress }
                    .take(8).map { it.hostAddress ?: "" }
                interfaces.put(JSONObject().put("name", nic.name.take(32)).put("mac", mac)
                    .put("addresses", JSONArray(addresses)))
            }
        } catch (_: SocketException) {
            // No guessed identifier: the screen reports metadata as unavailable.
        }
        if (factoryMac.isNotEmpty() && interfaces.length() < 12) interfaces.put(JSONObject()
            .put("name", "wifi-factory").put("mac", factoryMac).put("addresses", JSONArray()))
        return JSONObject().put("model", Build.MODEL.take(100)).put("serial", serial.take(100))
            .put("serial_source", if (serial.isEmpty()) "unavailable" else "android")
            .put("android", Build.VERSION.RELEASE.take(40)).put("apk", BuildConfig.VERSION_NAME)
            .put("network", network).put("interfaces", interfaces)
            .put("light_supported", RoomLight.supports(Build.MODEL, Build.DISPLAY))
    }
}
