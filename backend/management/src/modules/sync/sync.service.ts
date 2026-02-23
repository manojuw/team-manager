import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { SyncHistory } from '../database/entities/sync-history.entity';

@Injectable()
export class SyncService {
  constructor(
    @InjectRepository(SyncHistory)
    private readonly syncHistoryRepository: Repository<SyncHistory>,
  ) {}

  async getHistory(projectId: string, tenantId: string): Promise<SyncHistory[]> {
    return this.syncHistoryRepository.find({
      where: { project_id: projectId, tenant_id: tenantId },
      order: { started_at: 'DESC' },
      take: 50,
    });
  }

  async getStatus(projectId: string, tenantId: string) {
    const latest = await this.syncHistoryRepository.findOne({
      where: { project_id: projectId, tenant_id: tenantId },
      order: { started_at: 'DESC' },
    });

    if (!latest) {
      return { status: 'never_synced', lastSync: null };
    }

    return {
      status: latest.status,
      lastSync: latest.completed_at || latest.started_at,
      messagesAdded: latest.messages_added,
      messagesFetched: latest.messages_fetched,
      error: latest.error_message,
    };
  }
}
