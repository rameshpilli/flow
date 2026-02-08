import {
  Entity,
  Column,
  PrimaryGeneratedColumn,
  CreateDateColumn,
  UpdateDateColumn,
  Index,
} from 'typeorm';

/**
 * Compliance Record entity for tracking server compliance status and reviews
 */
@Entity({ name: 'compliance_records' })
@Index(['serverId'])
@Index(['status'])
export class ComplianceRecord {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column({ type: 'varchar', length: 255, nullable: false })
  serverId: string;

  @Index()
  @Column({ type: 'varchar', length: 255, nullable: false })
  serverName: string;

  @Column({ type: 'text', nullable: true })
  mcpUrl?: string;

  @Column({
    type: 'varchar',
    length: 50,
    nullable: false,
    default: 'pending_review',
  })
  status: string; // 'approved' | 'pending_review' | 'rejected' | 'suspended' | 'conditionally_approved'

  @Column({ type: 'int', nullable: true })
  complianceScore?: number; // 0-100

  @Column({ type: 'timestamp', nullable: true })
  reviewedAt?: Date;

  @Column({ type: 'varchar', length: 255, nullable: true })
  reviewedBy?: string;

  @Column({ type: 'text', nullable: true })
  reviewNotes?: string;

  @Column({ type: 'text', nullable: true })
  conditions?: string; // conditions for conditional approval

  @Column({ type: 'timestamp', nullable: true })
  expiresAt?: Date; // when approval expires

  @Column({ type: 'simple-json', nullable: true })
  ruleResults?: Record<string, any>; // stores rule evaluation results as JSON

  @Column({ type: 'simple-json', nullable: true })
  metadata?: Record<string, any>; // extra data

  @CreateDateColumn({ name: 'created_at', type: 'timestamp' })
  createdAt: Date;

  @UpdateDateColumn({ name: 'updated_at', type: 'timestamp' })
  updatedAt: Date;
}

export default ComplianceRecord;
