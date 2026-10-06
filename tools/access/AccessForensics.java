import com.healthmarketscience.jackcess.*;
import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Developer-only private extraction. No expressions, links, queries, macros or VBA run. */
public final class AccessForensics {
  public static void main(String[] args) throws Exception {
    if (args.length != 2) throw new IllegalArgumentException("source private-directory");
    Path output = Path.of(args[1]);
    Files.createDirectory(output);
    System.setProperty(Database.ALLOW_LINK_RESOLUTION_PROPERTY, "false");
    System.setProperty(Database.ENABLE_EXPRESSION_EVALUATION_PROPERTY, "false");
    try (Database db = new DatabaseBuilder(Path.of(args[0])).setReadOnly(true).open()) {
      db.setEvaluateExpressions(false);
      db.setDateTimeType(DateTimeType.LOCAL_DATE_TIME);
      db.setLinkResolver((a, b) -> { throw new IOException("Link resolution disabled"); });
      List<Object> tables = new ArrayList<>(), queries = new ArrayList<>();
      for (String name : db.getSystemTableNames()) {
        Table table = db.getSystemTable(name);
        List<Object> columns = new ArrayList<>();
        for (Column column : table.getColumns()) columns.add(CanamoAccess.object(
            "name", column.getName(), "type", column.getType().toString()));
        String filename = "system-" + tables.size() + ".jsonl";
        int rowNumber = 0;
        try (BufferedWriter writer = Files.newBufferedWriter(output.resolve(filename),
            java.nio.charset.StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW)) {
          for (Row original : table) {
            Map<String, Object> row = new LinkedHashMap<>();
            int columnNumber = 0;
            for (var cell : original.entrySet()) {
              Object value = cell.getValue();
              if (value instanceof byte[]) {
                byte[] bytes = (byte[]) value;
                String binary = "binary-" + tables.size() + "-" + rowNumber + "-" + columnNumber + ".dat";
                Files.write(output.resolve(binary), bytes, StandardOpenOption.CREATE_NEW);
                value = CanamoAccess.object("file", binary, "bytes", bytes.length);
              }
              row.put(cell.getKey(), value);
              columnNumber++;
            }
            writer.write(CanamoAccess.json(row)); writer.newLine(); rowNumber++;
          }
        }
        tables.add(CanamoAccess.object("name", name, "rows", rowNumber,
            "columns", columns, "file", filename));
      }
      for (var query : db.getQueries()) queries.add(CanamoAccess.object(
          "name", query.getName(), "type", query.getType().toString(), "sql", query.toSQLString()));
      Files.writeString(output.resolve("catalog.json"), CanamoAccess.json(CanamoAccess.object(
          "format", db.getFileFormat().name(), "tables", tables, "queries", queries)),
          java.nio.charset.StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
    }
  }
}
