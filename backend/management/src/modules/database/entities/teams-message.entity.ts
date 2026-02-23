import { Entity, PrimaryColumn, Column } from 'typeorm';

@Entity('teams_messages')
export class TeamsMessage {
  @PrimaryColumn({ type: 'text' })
  id: string;

  @Column({ type: 'text' })
  content: string;

  @Column({ type: 'text', nullable: true })
  sender: string;

  @Column({ type: 'text', nullable: true, name: 'created_at' })
  created_at: string;

  @Column({ type: 'text', nullable: true })
  team: string;

  @Column({ type: 'text', nullable: true })
  channel: string;

  @Column({ type: 'text', nullable: true, name: 'message_type' })
  message_type: string;

  @Column({ type: 'text', nullable: true, name: 'message_id' })
  message_id: string;

  @Column({ type: 'text', nullable: true, name: 'parent_message_id' })
  parent_message_id: string;

  @Column({ type: 'timestamptz', nullable: true, name: 'indexed_at' })
  indexed_at: Date;

  @Column({ type: 'text', nullable: true, name: 'project_id' })
  project_id: string;

  @Column({ type: 'uuid', nullable: true, name: 'tenant_id' })
  tenant_id: string;
}
