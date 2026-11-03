// Ghidra headless script: restore uploaded executable's own CVI symbols and decompile.
// @category ReverseEngineering
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.address.*;
import java.nio.file.*;
import java.io.*;
import java.util.*;

public class ExportCvi extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        List<String> lines = Files.readAllLines(Paths.get(args[0]));
        ArrayList<Function> app = new ArrayList<>();
        for (String line : lines) {
            String[] p = line.split("\\t");
            long n = Long.parseLong(p[0],16);
            Address a = toAddr(n);
            if (!currentProgram.getMemory().contains(a)) continue;
            String name = p[2];
            try {
                if (p[1].equals("1")) {
                    disassemble(a);
                    Function f = getFunctionAt(a);
                    if (f == null) f = createFunction(a,name);
                    if (f != null) {
                        f.setName(name,SourceType.USER_DEFINED);
                        if(n >= 0x4048f8L && n < 0x413200L) app.add(f);
                    }
                } else createLabel(a,name,true);
            } catch (Exception ex) { println(name+": "+ex); }
        }
        analyzeChanges(currentProgram);
        DecompInterface d = new DecompInterface();
        d.openProgram(currentProgram);
        try (PrintWriter out = new PrintWriter(args[1])) {
            for(Function f : app) {
                DecompileResults r = d.decompileFunction(f,60,monitor);
                out.println("\n/* ===== "+f.getName()+" @ "+f.getEntryPoint()+" ===== */");
                if (r.decompileCompleted()) out.println(r.getDecompiledFunction().getC());
                else out.println("/* ERROR "+r.getErrorMessage()+" */");
            }
        }
        d.dispose();
    }
}
