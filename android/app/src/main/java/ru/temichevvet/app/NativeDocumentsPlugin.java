package ru.temichevvet.app;

import android.content.Context;
import android.print.PrintManager;
import android.print.PrintAttributes;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "NativeDocuments")
public class NativeDocumentsPlugin extends Plugin {
    @PluginMethod public void print(PluginCall call) {
        getActivity().runOnUiThread(() -> {
            try {
                PrintManager manager = (PrintManager) getActivity().getSystemService(Context.PRINT_SERVICE);
                manager.print("TemichevVet — сводка", getBridge().getWebView().createPrintDocumentAdapter("TemichevVet"),
                    new PrintAttributes.Builder().setMediaSize(PrintAttributes.MediaSize.ISO_A4).build());
                call.resolve();
            } catch (Exception exception) {
                call.reject("Не удалось открыть печать", exception);
            }
        });
    }
}
