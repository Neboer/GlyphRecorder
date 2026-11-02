package dev.aaa1115910.glyphrecorder.diagnostics

import android.os.Binder
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import androidx.annotation.Keep
import dev.aaa1115910.glyphrecorder.IScreenCaptureService
import dev.aaa1115910.glyphrecorder.services.ScreenCaptureService

/** Root-only app_process probe. Never included in the release APK. */
@Keep
object CaptureLifecycleProbe {
    private const val SERVICE = "glyph_capture_lifecycle_probe"

    @JvmStatic
    fun main(args: Array<String>) {
        Looper.prepareMainLooper()
        val manager = Class.forName("android.os.ServiceManager")
        if (args.firstOrNull() == "server") {
            val service = ScreenCaptureService()
            manager.getMethod("addService", String::class.java, IBinder::class.java)
                .invoke(null, SERVICE, service)
            println("SERVER_READY")
            Looper.loop()
            return
        }
        val binder = manager.getMethod("getService", String::class.java).invoke(null, SERVICE) as IBinder
        val service = IScreenCaptureService.Stub.asInterface(binder)
        // This token lives in a different process from the service under test.
        service.attachClient(Binder())
        val handler = Handler(Looper.getMainLooper())
        Thread {
            try {
                if (args.firstOrNull() == "cycles") {
                    repeat(10) {
                        check(service.startScreenCapture())
                        // Restart while active also has to release the previous display.
                        check(service.startScreenCapture())
                        Thread.sleep(100)
                        service.stopScreenCapture()
                        service.stopScreenCapture() // Idempotent stop
                    }
                    println("CYCLES_PASSED")
                    runCatching { service.destroy() } // Process exit may close Binder before its reply.
                    handler.post { kotlin.system.exitProcess(0) }
                } else {
                    check(service.startScreenCapture())
                    println("CLIENT_READY")
                    // Host kills this process; the service must exit via linkToDeath.
                }
            } catch (error: Throwable) {
                error.printStackTrace()
                kotlin.system.exitProcess(1)
            }
        }.start()
        Looper.loop()
    }
}
