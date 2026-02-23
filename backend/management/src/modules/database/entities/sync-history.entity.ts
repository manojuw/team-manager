import { Entity, PrimaryGeneratedColumn, Column, CreateDateColumn } from 'typeorm';

@Entity('sync_history')
export class SyncHistory {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column({ type: 'uuid', name: 'tenant_id' })
  tenant_id: string;

  @Column({ type: 'uuid', name: 'project_id' })
  project_id: string;

  @Column({ type: 'uuid', name: 'data_source_id' })
  data_source_id: string;

  @Column({ type: 'text' })
  status: string;

  @Column({ type: 'int', nullable: true, name: 'messages_added' })
  messages_added: number;

  @Column({ type: 'int', nullable: true, name: 'messages_fetched' })
  messages_fetched: number;

  @Column({ type: 'text', nullable: true, name: 'error_message' })
  error_message: string;

  @CreateDateColumn({ name: 'started_at', type: 'timestamptz' })
  started_at: Date;

  @Column({ type: 'timestamptz', nullable: true, name: 'completed_at' })
  completed_at: Date;
}
