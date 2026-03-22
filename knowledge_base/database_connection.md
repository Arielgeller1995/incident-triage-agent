# Database Connection Issues

## Symptoms
- HikariCP / connection pool exhaustion errors
- "Connection is not available, request timed out"
- "remaining connection slots are reserved for non-replication superuser connections"
- "Too many connections" errors
- Slow queries or timeouts
- Services failing to start due to DB unavailability
- Active connections at maximum limit
- Large waiting queue for connections

## Likely Causes
- Connection pool size too small for current load
- Connection leaks — connections not properly closed after use
- Long-running transactions holding connections open
- Database server reached max_connections limit
- Application pods restarting repeatedly causing connection leaks
- Missing connection timeout or idle timeout configuration
- Sudden traffic spike exceeding pool capacity

## Diagnostic Steps
1. Check current connection count:
```sql
   SELECT count(*) FROM pg_stat_activity;
   SELECT state, count(*) FROM pg_stat_activity GROUP BY state;
```
2. Identify which services are consuming connections:
```sql
   SELECT application_name, client_addr, state, count(*) 
   FROM pg_stat_activity 
   GROUP BY application_name, client_addr, state;
```
3. Check for idle connections holding locks:
```sql
   SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state
   FROM pg_stat_activity
   WHERE state != 'idle' AND query_start < now() - interval '5 minutes';
```
4. Check HikariCP pool configuration in your app config or ConfigMap
5. Review application logs for connection leak warnings
6. Check database server max_connections setting:
```sql
   SHOW max_connections;
```

## Possible Fixes
- Increase `maximumPoolSize` in HikariCP configuration
- Reduce `connectionTimeout` to fail fast instead of queuing
- Set `idleTimeout` to reclaim unused connections
- Set `maxLifetime` to prevent stale connections
- Add connection leak detection: `leakDetectionThreshold=30000`
- Increase PostgreSQL `max_connections` in `postgresql.conf`
- Add a connection pooler like PgBouncer in front of PostgreSQL
- Fix connection leaks in application code — ensure connections are closed in finally blocks
- Scale down pods that are leaking connections

## Notes
- HikariCP default maximumPoolSize is 10 — often too low for production
- PostgreSQL default max_connections is 100 — shared across all services
- Connection leaks are often caused by exception paths that skip connection.close()
- PgBouncer can multiplex thousands of app connections into a small DB pool
- Monitor with: `SELECT count(*) FROM pg_stat_activity WHERE state = 'idle in transaction'`