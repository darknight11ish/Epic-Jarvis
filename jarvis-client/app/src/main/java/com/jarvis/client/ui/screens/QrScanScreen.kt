package com.jarvis.client.ui.screens

import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.google.zxing.BarcodeFormat
import com.google.zxing.BinaryBitmap
import com.google.zxing.DecodeHintType
import com.google.zxing.PlanarYUVLuminanceSource
import com.google.zxing.ReaderException
import com.google.zxing.common.HybridBinarizer
import com.google.zxing.qrcode.QRCodeReader
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/**
 * The camera view that reads the QR code on the PC (docs/PAIRING-DESIGN.md
 * §8.3), kept as small as it can be: CameraX shows the picture and hands
 * over frames, and ZXing's core library (plain Java, bundled, nothing
 * online) looks for a QR code in each one. No Google Play Services, no ML
 * Kit. Nothing is recorded, saved or sent: each frame is looked at once
 * and dropped.
 *
 * Only started after the owner tapped "Scan the code on your PC" and the
 * camera permission is granted - the caller checks both. [onText] gets the
 * text of every QR code seen, on the main thread; the caller decides
 * whether it is a Jarvis pairing code (Pairing.parseQr). [onError] is told
 * once if the camera cannot be started at all.
 */
@Composable
fun QrScanner(
    onText: (String) -> Unit,
    onError: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val latestOnText = rememberUpdatedState(onText)
    val latestOnError = rememberUpdatedState(onError)
    val previewView = remember {
        PreviewView(context).apply {
            // A TextureView underneath, so Compose can clip and place it like any view.
            implementationMode = PreviewView.ImplementationMode.COMPATIBLE
        }
    }

    DisposableEffect(lifecycleOwner) {
        val disposed = AtomicBoolean(false)
        val analysisThread = Executors.newSingleThreadExecutor()
        val mainThread = ContextCompat.getMainExecutor(context)
        val reader = QRCodeReader()
        val hints = mapOf(
            DecodeHintType.POSSIBLE_FORMATS to listOf(BarcodeFormat.QR_CODE),
        )
        var provider: ProcessCameraProvider? = null
        val future = ProcessCameraProvider.getInstance(context)
        future.addListener(
            {
                if (disposed.get()) return@addListener
                val p = runCatching { future.get() }.getOrNull()
                if (p == null) {
                    latestOnError.value()
                    return@addListener
                }
                provider = p
                val preview = Preview.Builder().build()
                preview.setSurfaceProvider(previewView.surfaceProvider)
                val analysis = ImageAnalysis.Builder()
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .build()
                analysis.setAnalyzer(analysisThread) { image ->
                    val text = decode(image, reader, hints)
                    image.close()
                    if (text != null && !disposed.get()) {
                        mainThread.execute { if (!disposed.get()) latestOnText.value(text) }
                    }
                }
                val bound = runCatching {
                    p.unbindAll()
                    p.bindToLifecycle(lifecycleOwner, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis)
                }
                if (bound.isFailure) latestOnError.value()
            },
            mainThread,
        )
        onDispose {
            disposed.set(true)
            runCatching { provider?.unbindAll() }
            analysisThread.shutdown()
        }
    }

    AndroidView(factory = { previewView }, modifier = modifier)
}

/**
 * The text of a QR code in [image], or null. Reads only the brightness
 * plane (the first plane of CameraX's YUV_420_888 frames), which is all a
 * QR code needs; ZXing finds a code at any rotation.
 */
private fun decode(image: ImageProxy, reader: QRCodeReader, hints: Map<DecodeHintType, Any>): String? {
    return try {
        val plane = image.planes[0]
        val buffer = plane.buffer
        val rowStride = plane.rowStride
        val width = image.width
        val height = image.height
        val data = ByteArray(rowStride * height)
        buffer.rewind()
        buffer.get(data, 0, minOf(buffer.remaining(), data.size))
        val source = PlanarYUVLuminanceSource(data, rowStride, height, 0, 0, width, height, false)
        reader.decode(BinaryBitmap(HybridBinarizer(source)), hints).text
    } catch (e: ReaderException) {
        // No QR code in this frame - the usual case.
        null
    } catch (e: RuntimeException) {
        // A frame of an unexpected shape: skip it, never crash the scanner.
        null
    } finally {
        reader.reset()
    }
}
