import { Controller, Get, Post, Put, Delete, Body, Param, UseGuards } from '@nestjs/common';
import { ConnectorsService } from './connectors.service';
import { CreateConnectorDto } from './dto/create-connector.dto';
import { UpdateConnectorDto } from './dto/update-connector.dto';
import { JwtAuthGuard } from '@/common/guards/jwt-auth.guard';
import { CurrentUser } from '@/common/decorators/current-user.decorator';
import { IAuthUser } from '@/common/interfaces/auth-user.interface';

@Controller('connectors')
@UseGuards(JwtAuthGuard)
export class ConnectorsController {
  constructor(private readonly connectorsService: ConnectorsService) {}

  @Post()
  async create(@Body() dto: CreateConnectorDto, @CurrentUser() user: IAuthUser) {
    return this.connectorsService.create(dto, user.tenantId);
  }

  @Get('project/:projectId')
  async findByProject(@Param('projectId') projectId: string, @CurrentUser() user: IAuthUser) {
    return this.connectorsService.findByProject(projectId, user.tenantId);
  }

  @Get(':id')
  async findOne(@Param('id') id: string, @CurrentUser() user: IAuthUser) {
    const connector = await this.connectorsService.findOneByTenant(id, user.tenantId);
    return connector;
  }

  @Put(':id')
  async update(
    @Param('id') id: string,
    @Body() dto: UpdateConnectorDto,
    @CurrentUser() user: IAuthUser,
  ) {
    return this.connectorsService.update(id, dto, user.tenantId);
  }

  @Delete(':id')
  async remove(@Param('id') id: string, @CurrentUser() user: IAuthUser) {
    await this.connectorsService.remove(id, user.tenantId);
    return { success: true };
  }
}
