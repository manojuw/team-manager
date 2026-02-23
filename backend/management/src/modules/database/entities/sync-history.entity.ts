import { Entity, PrimaryGeneratedColumn, Column, CreateDateColumn } from 'typeorm';

@Entity('sync_history')
export class SyncHistory {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column({ type: 'uuid', name: 'tenant_id' })
  tenant_id: string;

  @Column({ type: 'text', name: 'project_id' })
  project_id: string;

  @Column({ type: 'text', nullable: true, name: 'connector_id' })
  connector_id: string;

  @Column({ type: 'text', nullable: true, name: 'data_source_id' })
  data_source_id: string;

  @Column({ type: 'text', nullable: true, name: 'source_type' })
  source_type: string;

  @Column({ type: 'text', nullable: true, name: 'segment_type' })
  segment_type: string;

  @Column({ type: 'text' })
  status: string;

  @Column({ type: 'int', nullable: true, name: 'records_added' })
  records_added: number;

  @Column({ type: 'int', nullable: true, name: 'records_fetched' })
  records_fetched: number;

  @Column({ type: 'text', nullable: true, name: 'error_message' })
  error_message: string;

  @CreateDateColumn({ name: 'started_at', type: 'timestamptz' })
  started_at: Date;

  @Column({ type: 'timestamptz', nullable: true, name: 'completed_at' })
  completed_at: Date;
}
