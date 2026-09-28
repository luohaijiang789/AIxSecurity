import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.RandomAccessFile;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.sql.Connection;
import java.sql.Statement;
import java.sql.PreparedStatement;
import javax.servlet.http.HttpServletRequest;

// Synthetic, source-only rule fixtures: never executed as an application.
class Profiles {
    void sqlUnsafe(HttpServletRequest request, Statement statement) throws Exception {
        String input = request.getParameter("id");
        // ruleid: aix.java.sqli.taint
        statement.executeQuery("select * from users where id='" + input + "'");
    }
    void sqlBound(HttpServletRequest request, Connection connection) throws Exception {
        String input = request.getParameter("id");
        // ok: aix.java.sqli.taint
        PreparedStatement query = connection.prepareStatement("select * from users where id=?");
        query.setString(1, input);
        // ok: aix.java.sqli.taint
        query.executeQuery();
    }
    void runtimeCommand(HttpServletRequest request) throws Exception {
        String input = request.getParameter("cmd");
        // ruleid: aix.java.command-injection.taint
        Runtime.getRuntime().exec(input);
    }
    void runtimeFixed(HttpServletRequest request) throws Exception {
        String unused = request.getParameter("cmd");
        // ok: aix.java.command-injection.taint
        Runtime.getRuntime().exec("/usr/bin/true");
    }
    void explicitShell(HttpServletRequest request) throws Exception {
        String input = request.getHeader("X-Command");
        // ruleid: aix.java.command-injection.taint
        new ProcessBuilder("/bin/sh", "-c", input).start();
    }
    void ordinaryArgument(HttpServletRequest request) throws Exception {
        String input = request.getParameter("text");
        // ok: aix.java.command-injection.taint
        new ProcessBuilder("/usr/bin/printf", "%s", input).start();
    }
    void shellNotStarted(HttpServletRequest request) throws Exception {
        String input = request.getParameter("text");
        // ok: aix.java.command-injection.taint
        ProcessBuilder builder = new ProcessBuilder("sh", "-c", input);
    }
    void fixedShellWithUserEnv(HttpServletRequest request) throws Exception {
        String input = request.getParameter("text");
        // ok: aix.java.command-injection.taint
        Runtime.getRuntime().exec("/usr/bin/true", new String[]{input});
    }
    void fileRead(HttpServletRequest request) throws Exception {
        String name = request.getParameter("name");
        // ruleid: aix.java.path-traversal.taint
        new FileInputStream("/srv/files/" + name);
    }
    void nioRead(HttpServletRequest request) throws Exception {
        String name = request.getParameter("name");
        // ruleid: aix.java.path-traversal.taint
        Files.readAllBytes(Paths.get("/srv/files/", name));
    }
    void normalizedStillUnconfined(HttpServletRequest request) throws Exception {
        String name = request.getParameter("name");
        // ruleid: aix.java.path-traversal.taint
        Files.newInputStream(Paths.get("/srv/files/", name).normalize());
    }
    void fixedFile(HttpServletRequest request) throws Exception {
        String unused = request.getParameter("name");
        // ok: aix.java.path-traversal.taint
        new FileInputStream("/srv/files/fixed.txt");
    }
    void pathObjectOnly(HttpServletRequest request) throws Exception {
        String name = request.getParameter("name");
        // ok: aix.java.path-traversal.taint
        File file = new File(name);
    }
    void fixedPathUserContent(HttpServletRequest request) throws Exception {
        String data = request.getParameter("text");
        // ok: aix.java.path-traversal.taint
        Files.write(Paths.get("/srv/files/fixed.txt"), data.getBytes());
    }
    void runtimeVariable(HttpServletRequest request) throws Exception {
        String input = request.getParameter("cmd");
        Runtime runtime = Runtime.getRuntime();
        // ruleid: aix.java.command-injection.taint
        runtime.exec("echo " + input, new String[]{}, new java.io.File("/tmp"));
    }
    void fullyQualifiedRuntime(HttpServletRequest request) throws Exception {
        String input = request.getParameter("cmd");
        java.lang.Runtime runtime = java.lang.Runtime.getRuntime();
        // ruleid: aix.java.command-injection.taint
        runtime.exec(input);
    }
    void typedRuntimeFixedCommand(HttpServletRequest request) throws Exception {
        String input = request.getParameter("env");
        Runtime runtime = Runtime.getRuntime();
        // ok: aix.java.command-injection.taint
        runtime.exec("/usr/bin/true", new String[]{input});
    }
    void unrelatedExec(HttpServletRequest request, Other other) throws Exception {
        String input = request.getParameter("text");
        // ok: aix.java.command-injection.taint
        other.exec(input);
    }
    void qualifiedFileWrapper(HttpServletRequest request) throws Exception {
        String input = request.getParameter("file");
        // ruleid: aix.java.path-traversal.taint
        new java.io.FileInputStream(new java.io.File("/srv/files/" + input));
    }
    void fileWrapperVariable(HttpServletRequest request) throws Exception {
        String input = request.getParameter("file");
        java.io.File file = new java.io.File(input);
        // ruleid: aix.java.path-traversal.taint
        new java.io.FileInputStream(file);
    }
    void qualifiedNioRead(HttpServletRequest request) throws Exception {
        String input = request.getParameter("file");
        // ruleid: aix.java.path-traversal.taint
        java.nio.file.Files.readAllBytes(java.nio.file.Paths.get(input));
    }
    void qualifiedFileWrapperConstant(HttpServletRequest request) throws Exception {
        String unused = request.getParameter("file");
        // ok: aix.java.path-traversal.taint
        new java.io.FileInputStream(new java.io.File("/srv/files/fixed.txt"));
    }
    void qualifiedFileObjectOnly(HttpServletRequest request) throws Exception {
        String input = request.getParameter("file");
        // ok: aix.java.path-traversal.taint
        java.io.File file = new java.io.File(input);
    }
}
class Other { void exec(String value) {} }
