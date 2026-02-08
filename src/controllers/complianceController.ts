import { Request, Response } from 'express';
import { getAppDataSource } from '../db/connection.js';
import { ComplianceRecord } from '../db/entities/ComplianceRecord.js';
import { ComplianceAuditLog } from '../db/entities/ComplianceAuditLog.js';

/**
 * Helper function to create an audit log entry
 */
const createAuditLog = async (
  serverId: string,
  eventType: string,
  details?: string,
  previousStatus?: string,
  newStatus?: string,
  metadata?: Record<string, any>,
  actor?: string,
): Promise<void> => {
  try {
    const dataSource = getAppDataSource();
    const auditRepo = dataSource.getRepository(ComplianceAuditLog);

    await auditRepo.save({
      serverId,
      eventType,
      details,
      previousStatus,
      newStatus,
      metadata,
      actor,
    });
  } catch (error) {
    console.error('Failed to create audit log:', error);
    // Don't throw - audit log failure should not block the main operation
  }
};

/**
 * GET /compliance/status/:serverId - Get compliance status for a specific server
 */
export const getComplianceStatus = async (req: Request, res: Response): Promise<void> => {
  try {
    const { serverId } = req.params;

    if (!serverId) {
      res.status(400).json({
        success: false,
        message: 'Server ID is required',
      });
      return;
    }

    const dataSource = getAppDataSource();
    const complianceRepo = dataSource.getRepository(ComplianceRecord);

    const record = await complianceRepo.findOne({
      where: { serverId },
    });

    if (!record) {
      res.status(404).json({
        success: false,
        message: 'Compliance record not found for this server',
      });
      return;
    }

    res.json({
      success: true,
      data: record,
    });
  } catch (error) {
    console.error('Failed to get compliance status:', error);
    res.status(500).json({
      success: false,
      message: 'Failed to get compliance status',
    });
  }
};

/**
 * GET /compliance/servers - List all compliance records with optional filtering
 */
export const getAllComplianceRecords = async (req: Request, res: Response): Promise<void> => {
  try {
    const status = req.query.status as string | undefined;

    const dataSource = getAppDataSource();
    const complianceRepo = dataSource.getRepository(ComplianceRecord);

    let query = complianceRepo.createQueryBuilder('cr');

    if (status) {
      query = query.where('cr.status = :status', { status });
    }

    const records = await query.orderBy('cr.createdAt', 'DESC').getMany();

    res.json({
      success: true,
      data: records,
    });
  } catch (error) {
    console.error('Failed to get compliance records:', error);
    res.status(500).json({
      success: false,
      message: 'Failed to get compliance records',
    });
  }
};

/**
 * POST /compliance/check - Trigger compliance evaluation for a server
 */
export const checkCompliance = async (req: Request, res: Response): Promise<void> => {
  try {
    const { serverId, serverName, mcpUrl } = req.body;

    if (!serverId || !serverName) {
      res.status(400).json({
        success: false,
        message: 'Server ID and server name are required',
      });
      return;
    }

    const dataSource = getAppDataSource();
    const complianceRepo = dataSource.getRepository(ComplianceRecord);

    // Check if record already exists
    let record = await complianceRepo.findOne({
      where: { serverId },
    });

    if (!record) {
      // Create new record
      record = complianceRepo.create({
        serverId,
        serverName,
        mcpUrl: mcpUrl || null,
        status: 'pending_review',
      });

      await complianceRepo.save(record);

      // Create audit log for registration
      await createAuditLog(
        serverId,
        'registered',
        `Server ${serverName} registered for compliance review`,
        undefined,
        'pending_review',
        { mcpUrl },
      );
    } else {
      // Update status to pending_review if not already
      const previousStatus = record.status;
      record.status = 'pending_review';
      await complianceRepo.save(record);

      if (previousStatus !== 'pending_review') {
        await createAuditLog(
          serverId,
          'rule_evaluated',
          `Compliance evaluation triggered for server ${serverName}`,
          previousStatus,
          'pending_review',
        );
      }
    }

    res.json({
      success: true,
      data: record,
      message: 'Compliance check initiated',
    });
  } catch (error) {
    console.error('Failed to check compliance:', error);
    res.status(500).json({
      success: false,
      message: 'Failed to initiate compliance check',
    });
  }
};

/**
 * POST /compliance/approve/:serverId - Approve a server
 */
export const approveServer = async (req: Request, res: Response): Promise<void> => {
  try {
    const { serverId } = req.params;
    const { reviewer, notes, expiresAt, conditions } = req.body;

    if (!serverId) {
      res.status(400).json({
        success: false,
        message: 'Server ID is required',
      });
      return;
    }

    if (!reviewer) {
      res.status(400).json({
        success: false,
        message: 'Reviewer name is required',
      });
      return;
    }

    const dataSource = getAppDataSource();
    const complianceRepo = dataSource.getRepository(ComplianceRecord);

    const record = await complianceRepo.findOne({
      where: { serverId },
    });

    if (!record) {
      res.status(404).json({
        success: false,
        message: 'Compliance record not found',
      });
      return;
    }

    const previousStatus = record.status;

    // Determine if it's conditional or full approval
    const newStatus = conditions ? 'conditionally_approved' : 'approved';

    record.status = newStatus;
    record.reviewedAt = new Date();
    record.reviewedBy = reviewer;
    record.reviewNotes = notes || null;
    record.expiresAt = expiresAt ? new Date(expiresAt) : null;
    record.conditions = conditions || null;

    await complianceRepo.save(record);

    // Create audit log
    await createAuditLog(
      serverId,
      'approved',
      `Server approved by ${reviewer}${notes ? ': ' + notes : ''}`,
      previousStatus,
      newStatus,
      { expiresAt, conditions },
      reviewer,
    );

    res.json({
      success: true,
      data: record,
      message: `Server ${newStatus === 'conditionally_approved' ? 'conditionally approved' : 'approved'} successfully`,
    });
  } catch (error) {
    console.error('Failed to approve server:', error);
    res.status(500).json({
      success: false,
      message: 'Failed to approve server',
    });
  }
};

/**
 * POST /compliance/reject/:serverId - Reject a server
 */
export const rejectServer = async (req: Request, res: Response): Promise<void> => {
  try {
    const { serverId } = req.params;
    const { reviewer, notes } = req.body;

    if (!serverId) {
      res.status(400).json({
        success: false,
        message: 'Server ID is required',
      });
      return;
    }

    if (!reviewer) {
      res.status(400).json({
        success: false,
        message: 'Reviewer name is required',
      });
      return;
    }

    const dataSource = getAppDataSource();
    const complianceRepo = dataSource.getRepository(ComplianceRecord);

    const record = await complianceRepo.findOne({
      where: { serverId },
    });

    if (!record) {
      res.status(404).json({
        success: false,
        message: 'Compliance record not found',
      });
      return;
    }

    const previousStatus = record.status;

    record.status = 'rejected';
    record.reviewedAt = new Date();
    record.reviewedBy = reviewer;
    record.reviewNotes = notes || null;

    await complianceRepo.save(record);

    // Create audit log
    await createAuditLog(
      serverId,
      'rejected',
      `Server rejected by ${reviewer}${notes ? ': ' + notes : ''}`,
      previousStatus,
      'rejected',
      undefined,
      reviewer,
    );

    res.json({
      success: true,
      data: record,
      message: 'Server rejected successfully',
    });
  } catch (error) {
    console.error('Failed to reject server:', error);
    res.status(500).json({
      success: false,
      message: 'Failed to reject server',
    });
  }
};

/**
 * POST /compliance/suspend/:serverId - Suspend a server
 */
export const suspendServer = async (req: Request, res: Response): Promise<void> => {
  try {
    const { serverId } = req.params;
    const { reason } = req.body;

    if (!serverId) {
      res.status(400).json({
        success: false,
        message: 'Server ID is required',
      });
      return;
    }

    if (!reason) {
      res.status(400).json({
        success: false,
        message: 'Suspension reason is required',
      });
      return;
    }

    const dataSource = getAppDataSource();
    const complianceRepo = dataSource.getRepository(ComplianceRecord);

    const record = await complianceRepo.findOne({
      where: { serverId },
    });

    if (!record) {
      res.status(404).json({
        success: false,
        message: 'Compliance record not found',
      });
      return;
    }

    const previousStatus = record.status;

    record.status = 'suspended';
    record.reviewNotes = reason;

    await complianceRepo.save(record);

    // Create audit log
    await createAuditLog(
      serverId,
      'suspended',
      `Server suspended: ${reason}`,
      previousStatus,
      'suspended',
      { reason },
    );

    res.json({
      success: true,
      data: record,
      message: 'Server suspended successfully',
    });
  } catch (error) {
    console.error('Failed to suspend server:', error);
    res.status(500).json({
      success: false,
      message: 'Failed to suspend server',
    });
  }
};

/**
 * GET /compliance/audit/:serverId - Get audit trail for a server
 */
export const getAuditLog = async (req: Request, res: Response): Promise<void> => {
  try {
    const { serverId } = req.params;
    const limit = req.query.limit ? parseInt(req.query.limit as string, 10) : 100;

    if (!serverId) {
      res.status(400).json({
        success: false,
        message: 'Server ID is required',
      });
      return;
    }

    if (isNaN(limit) || limit < 1 || limit > 1000) {
      res.status(400).json({
        success: false,
        message: 'Limit must be a number between 1 and 1000',
      });
      return;
    }

    const dataSource = getAppDataSource();
    const auditRepo = dataSource.getRepository(ComplianceAuditLog);

    const logs = await auditRepo
      .createQueryBuilder('cal')
      .where('cal.serverId = :serverId', { serverId })
      .orderBy('cal.createdAt', 'DESC')
      .limit(limit)
      .getMany();

    res.json({
      success: true,
      data: logs,
    });
  } catch (error) {
    console.error('Failed to get audit log:', error);
    res.status(500).json({
      success: false,
      message: 'Failed to get audit log',
    });
  }
};

/**
 * GET /compliance/dashboard - Get compliance dashboard summary statistics
 */
export const getComplianceDashboard = async (req: Request, res: Response): Promise<void> => {
  try {
    const dataSource = getAppDataSource();
    const complianceRepo = dataSource.getRepository(ComplianceRecord);

    const totalServers = await complianceRepo.count();

    const approvedCount = await complianceRepo.count({
      where: { status: 'approved' },
    });

    const conditionallyApprovedCount = await complianceRepo.count({
      where: { status: 'conditionally_approved' },
    });

    const pendingCount = await complianceRepo.count({
      where: { status: 'pending_review' },
    });

    const rejectedCount = await complianceRepo.count({
      where: { status: 'rejected' },
    });

    const suspendedCount = await complianceRepo.count({
      where: { status: 'suspended' },
    });

    res.json({
      success: true,
      data: {
        total: totalServers,
        approved: approvedCount,
        conditionallyApproved: conditionallyApprovedCount,
        pendingReview: pendingCount,
        rejected: rejectedCount,
        suspended: suspendedCount,
      },
    });
  } catch (error) {
    console.error('Failed to get compliance dashboard:', error);
    res.status(500).json({
      success: false,
      message: 'Failed to get compliance dashboard',
    });
  }
};
