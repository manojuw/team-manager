import { Controller, Get, Param, UseGuards } from '@nestjs/common';
import { SyncService } from './sync.service';
import { JwtAuthGuard } from '@/common/guards/jwt-auth.guard';
import { CurrentUser } from '@/common/decorators/current-user.decorator';
import { IAuthUser } from '@/common/interfaces/auth-user.interface';

@Controller('sync')
@UseGuards(JwtAuthGuard)
export class SyncController {
  constructor(private readonly syncService: SyncService) {}

  @Get('history/:projectId')
  async getHistory(@Param('projectId') projectId: string, @CurrentUser() user: IAuthUser) {
    return this.syncService.getHistory(projectId, user.tenantId);
  }

  @Get('status/:projectId')
  async getStatus(@Param('projectId') projectId: string, @CurrentUser() user: IAuthUser) {
    return this.syncService.getStatus(projectId, user.tenantId);
  }
}
