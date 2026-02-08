import 'reflect-metadata';
import { DataSource } from 'typeorm';
import { ComplianceRecord } from './entities/ComplianceRecord.js';
import { ComplianceAuditLog } from './entities/ComplianceAuditLog.js';

/**
 * Separate data source for compliance entities.
 * Uses sql.js (pure JS SQLite) when PostgreSQL is not available.
 * This allows the compliance module to work independently of the main MCPHub database.
 */

let complianceDataSource: DataSource | null = null;
let initPromise: Promise<DataSource> | null = null;

const complianceEntities = [ComplianceRecord, ComplianceAuditLog];

/**
 * Initialize the compliance database.
 * - If DB_URL is set, connects to PostgreSQL (shared with main MCPHub DB)
 * - Otherwise, uses a local SQLite file via sql.js
 */
export const initializeComplianceDb = async (): Promise<DataSource> => {
  if (initPromise) {
    return initPromise;
  }

  if (complianceDataSource?.isInitialized) {
    return complianceDataSource;
  }

  initPromise = doInit();
  try {
    return await initPromise;
  } catch (err) {
    initPromise = null;
    throw err;
  }
};

const doInit = async (): Promise<DataSource> => {
  const dbUrl = process.env.DB_URL;

  if (dbUrl) {
    // Use PostgreSQL — share the same database as MCPHub
    console.log('[Compliance DB] Using PostgreSQL for compliance data');
    complianceDataSource = new DataSource({
      type: 'postgres',
      url: dbUrl,
      synchronize: true,
      entities: complianceEntities,
    });
  } else {
    // Use sql.js (pure JS SQLite) for local dev / testing
    const dbPath = process.env.COMPLIANCE_DB_PATH || './compliance.sqlite';
    console.log(`[Compliance DB] Using SQLite (sql.js) at: ${dbPath}`);
    complianceDataSource = new DataSource({
      type: 'sqljs',
      location: dbPath,
      autoSave: true,
      synchronize: true,
      entities: complianceEntities,
    });
  }

  await complianceDataSource.initialize();
  console.log('[Compliance DB] Database initialized successfully');
  return complianceDataSource;
};

/**
 * Get the compliance data source. Throws if not initialized.
 */
export const getComplianceDataSource = (): DataSource => {
  if (!complianceDataSource?.isInitialized) {
    throw new Error('Compliance database not initialized. Call initializeComplianceDb() first.');
  }
  return complianceDataSource;
};

/**
 * Check if compliance database is connected
 */
export const isComplianceDbConnected = (): boolean => {
  return complianceDataSource?.isInitialized ?? false;
};

/**
 * Close the compliance database connection
 */
export const closeComplianceDb = async (): Promise<void> => {
  if (complianceDataSource?.isInitialized) {
    await complianceDataSource.destroy();
    console.log('[Compliance DB] Connection closed');
  }
  complianceDataSource = null;
  initPromise = null;
};
