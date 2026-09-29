import com.healthmarketscience.jackcess.*;
import java.io.*;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.*;
import java.util.*;

/** Local table reader. Never evaluates expressions, queries, VBA or linked tables. */
public final class CanamoAccess {
  static Map<String,Object> object(Object... pairs) {
    Map<String,Object> result = new LinkedHashMap<>();
    for (int i=0;i<pairs.length;i+=2) result.put((String)pairs[i],pairs[i+1]);
    return result;
  }
  static String json(Object value) {
    if(value==null) return "null";
    if(value instanceof Boolean || value instanceof Integer || value instanceof Long || value instanceof Short || value instanceof Byte) return value.toString();
    // Decimal and floating point input are represented as strings, never rounded by JSON consumers.
    if(value instanceof BigDecimal) return json(((BigDecimal)value).toPlainString());
    if(value instanceof byte[]) return json(object("$binary", Base64.getEncoder().encodeToString((byte[])value)));
    if(value instanceof Map<?,?>) {
      List<String> parts=new ArrayList<>();
      for(Map.Entry<?,?> entry:((Map<?,?>)value).entrySet()) parts.add(json(entry.getKey().toString())+":"+json(entry.getValue()));
      return "{"+String.join(",",parts)+"}";
    }
    if(value instanceof Iterable<?>) {
      List<String> parts=new ArrayList<>(); for(Object item:(Iterable<?>)value) parts.add(json(item));
      return "["+String.join(",",parts)+"]";
    }
    if(!(value instanceof CharSequence || value instanceof Number || value instanceof java.time.temporal.TemporalAccessor || value instanceof UUID))
      return json(object("$opaque_type",value.getClass().getName(),"value",value.toString()));
    StringBuilder out=new StringBuilder("\"");
    for(char c:value.toString().toCharArray()) {
      switch(c) { case '"':out.append("\\\"");break; case '\\':out.append("\\\\");break;
        case '\n':out.append("\\n");break;case '\r':out.append("\\r");break;case '\t':out.append("\\t");break;
        default: if(c<32) out.append(String.format("\\u%04x",(int)c)); else out.append(c);
      }
    }
    return out.append('"').toString();
  }
  static void extract(Path source,Path destination) throws Exception {
    System.setProperty(Database.ALLOW_LINK_RESOLUTION_PROPERTY,"false");
    System.setProperty(Database.ENABLE_EXPRESSION_EVALUATION_PROPERTY,"false");
    Files.createDirectories(destination);
    List<Object> tables=new ArrayList<>(), queries=new ArrayList<>();
    try(Database db=new DatabaseBuilder(source).setReadOnly(true).open()) {
      db.setEvaluateExpressions(false);
      db.setDateTimeType(DateTimeType.LOCAL_DATE_TIME);
      db.setLinkResolver((linker,name)-> {throw new IOException("Linked sources are disabled");});
      int tableNumber=0;
      for(TableMetaData metadata:db.newTableMetaDataIterable()) {
        if(metadata.isSystem()) continue;
        if(metadata.isLinked()) {
          // Connection strings may contain credentials. Report only the fact/type/name.
          tables.add(object("name",metadata.getName(),"linked",true,"type",metadata.getType().toString(),"columns",List.of(),"rows",null));
          continue;
        }
        Table table=db.getTable(metadata.getName());
        List<Object> columns=new ArrayList<>(), keys=new ArrayList<>();
        for(Column column:table.getColumns()) columns.add(object("name",column.getName(),"type",column.getType().toString(),"calculated",column.isCalculated(),"precision",(int)column.getPrecision(),"scale",(int)column.getScale()));
        for(Index index:table.getIndexes()) if(index.isPrimaryKey()) for(Index.Column c:index.getColumns()) keys.add(c.getName());
        String filename="table-"+(tableNumber++)+".jsonl";
        long count=0;
        try(BufferedWriter writer=Files.newBufferedWriter(destination.resolve(filename),StandardCharsets.UTF_8,StandardOpenOption.CREATE_NEW)) {
          for(Row row:table) {writer.write(json(row));writer.newLine();count++;}
        }
        if(count!=table.getRowCount()) throw new IOException("Row count differs: "+table.getName());
        tables.add(object("name",table.getName(),"linked",false,"columns",columns,"primary_key",keys,"rows",count,"file",filename));
      }
      // Names and types only: no execution or expansion of query SQL / external paths.
      for(var query:db.getQueries()) queries.add(object("name",query.getName(),"type",query.getType().toString()));
      Map<String,Object> manifest=object("format","canamo-access-raw-v1","engine","Jackcess 5.0.1","database_format",db.getFileFormat().toString(),"read_only",true,"expressions",false,"links_followed",0,"password_protected",db.getDatabasePassword()!=null&&!db.getDatabasePassword().isEmpty(),"tables",tables,"queries",queries);
      Files.writeString(destination.resolve("manifest.json"),json(manifest),StandardCharsets.UTF_8,StandardOpenOption.CREATE_NEW);
    }
  }
  static void fixture(Path destination,String kind) throws Exception {
    if(Files.exists(destination)) throw new IOException("Fixture destination exists");
    try(Database db=DatabaseBuilder.create(kind.startsWith("mdb")?Database.FileFormat.V2000:Database.FileFormat.V2010,destination.toFile())) {
      Table customers=new TableBuilder("Clientes").addColumn(new ColumnBuilder("Cod_cli",DataType.TEXT).setLengthInUnits(20))
        .addColumn(new ColumnBuilder("Cliente",DataType.TEXT).setLengthInUnits(100))
        .addColumn(new ColumnBuilder("Telefono1",DataType.TEXT).setLengthInUnits(20))
        .addColumn(new ColumnBuilder("Matricula",DataType.TEXT).setLengthInUnits(20))
        .addColumn(new ColumnBuilder("Notas",DataType.MEMO)).setPrimaryKey("Cod_cli").toTable(db);
      customers.addRow("001","Cliente sintético Álvarez","600000001","1234-XYZ","Línea uno\nLínea dos; €");
      customers.addRow("002","Cliente sintético Muñoz","600000002","5678 XYZ","Texto conservado");
      Table invoices=new TableBuilder("Facturas").addColumn(new ColumnBuilder("COD_CLI",DataType.TEXT).setLengthInUnits(20))
        .addColumn(new ColumnBuilder("FACTURA",DataType.TEXT).setLengthInUnits(30))
        .addColumn(new ColumnBuilder("FECHA",DataType.SHORT_DATE_TIME))
        .addColumn(new ColumnBuilder("BASE",DataType.MONEY)).addColumn(new ColumnBuilder("IVA",DataType.MONEY))
        .addColumn(new ColumnBuilder("TOTAL",DataType.MONEY)).setPrimaryKey("COD_CLI","FACTURA").toTable(db);
      invoices.addRow("001","0007",LocalDateTime.of(2010,3,28,1,30),new BigDecimal("10.0000"),new BigDecimal("1.6000"),new BigDecimal("11.6000"));
      invoices.addRow("002","0007",LocalDateTime.of(2010,10,31,2,30),new BigDecimal("20.0000"),new BigDecimal("3.6000"),new BigDecimal("23.6000"));
      Table lines=new TableBuilder("DETALLE").addColumn(new ColumnBuilder("COD_CLI",DataType.TEXT).setLengthInUnits(20))
        .addColumn(new ColumnBuilder("FACTURA",DataType.TEXT).setLengthInUnits(30))
        .addColumn(new ColumnBuilder("CANTIDAD",DataType.MONEY)).addColumn(new ColumnBuilder("CONCEPTO",DataType.MEMO))
        .addColumn(new ColumnBuilder("PRECIO",DataType.MONEY)).addColumn(new ColumnBuilder("TOTAL",DataType.MONEY))
        .addColumn(new ColumnBuilder("TIPO_IVA",DataType.MONEY)).toTable(db);
      lines.addRow("001","0007",new BigDecimal("1.0000"),"Trabajo sintético IVA antiguo",new BigDecimal("10.0000"),new BigDecimal("10.0000"),new BigDecimal("16.0000"));
      lines.addRow("002","0007",new BigDecimal("2.0000"),"Otra factura con igual número",new BigDecimal("10.0000"),new BigDecimal("20.0000"),new BigDecimal("18.0000"));
      db.createLinkedTable("Vinculo_no_abrir","\\\\invalid.example\\private\\forbidden.mdb","Remota");
      if(kind.endsWith("-copy")) {
        Table unrelated=new TableBuilder("Tabla adicional sin mapear").addColumn(new ColumnBuilder("Nota",DataType.TEXT).setLengthInUnits(100)).toTable(db);
        unrelated.addRow("Cambio físico de la copia, sin cambiar clientes/facturas");
      }
    }
  }
  public static void main(String[] args) {
    try {
      if(args.length==3&&args[0].equals("extract")) extract(Path.of(args[1]),Path.of(args[2]));
      else if(args.length==3&&args[0].equals("fixture")) fixture(Path.of(args[1]),args[2]);
      else throw new IllegalArgumentException("extract source destination | fixture destination mdb|accdb");
    } catch(Exception failure) {
      // No stack dump or database password/connection string in logs.
      System.err.println(json(object("error",failure.getClass().getSimpleName(),"message","No se ha podido leer la copia. Compruebe formato, cifrado y permisos; use la exportación CSV si procede.")));
      System.exit(2);
    }
  }
}
