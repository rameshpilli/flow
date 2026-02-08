import { Entity, Column, PrimaryGeneratedColumn, CreateDateColumn, Index } from 'typeorm';

/**
 * Compliance Audit Log entity for tracking compliance-related events and status changes
 */
@Entity({ name: 'compliance_audit_logs' })
@Index(['serverId'])
@Index(['eventType'])
@Index(['createdAt'])
export class ComplianceAuditLog {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column({ type: 'varchar', length: 255, nullable: false })
  serverId: string;

  @Column({ type: 'varchar', length: 100, nullable: false })
  eventType: string; // 'registered' | 'approved' | 'rejected' | 'suspended' | 'connection_blocked' | 'connection_allowed' | 'rule_evaluated'

  @Column({ type: 'varchar', length: 255, nullable: true })
  actor?: string; // who performed the action

  @Column({ type: 'text', nullable: true })
  details?: string; // description of what happened

  @Column({ type: 'varchar', length: 50, nullable: true })
  previousStatus?: string;

  @Column({ type: 'varchar', length: 50, nullable: true })
  newStatus?: string;

  @Column({ type: 'simple-json', nullable: true })
  metadata?: Record<string, any>;

  @CreateDateColumn({ name: 'created_at', type: 'timestamp' })
  createdAt: Date;
}

export default ComplianceAuditLog;
