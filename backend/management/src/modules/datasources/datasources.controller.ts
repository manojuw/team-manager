import { Controller, Get, Post, Put, Delete, Body, Param, UseGuards } from '@nestjs/common';
import { DataSourcesService } from './datasources.service';
import { CreateDataSourceDto } from './dto/create-datasource.dto';
import { UpdateDataSourceDto } from './dto/update-datasource.dto';
import { JwtAuthGuard } from '@/common/guards/jwt-auth.guard';
import { CurrentUser } from '@/common/decorators/current-user.decorator';
import { IAuthUser } from '@/common/interfaces/auth-user.interface';

@Controller('datasources')
@UseGuards(JwtAuthGuard)
export class DataSourcesController {
  constructor(private readonly dataSourcesService: DataSourcesService) {}

  @Post()
  async create(@Body() dto: CreateDataSourceDto, @CurrentUser() user: IAuthUser) {
    return this.dataSourcesService.create(dto, user.tenantId);
  }

  @Get('connector/:connectorId')
  async findByConnector(@Param('connectorId') connectorId: string, @CurrentUser() user: IAuthUser) {
    return this.dataSourcesService.findByConnector(connectorId, user.tenantId);
  }

  @Get('project/:projectId')
  async findByProject(@Param('projectId') projectId: string, @CurrentUser() user: IAuthUser) {
    return this.dataSourcesService.findByProject(projectId, user.tenantId);
  }

  @Get(':id')
  async findOne(@Param('id') id: string, @CurrentUser() user: IAuthUser) {
    return this.dataSourcesService.findOneByTenant(id, user.tenantId);
  }

  @Put(':id')
  async update(
    @Param('id') id: string,
    @Body() dto: UpdateDataSourceDto,
    @CurrentUser() user: IAuthUser,
  ) {
    return this.dataSourcesService.update(id, dto, user.tenantId);
  }

  @Delete(':id')
  async remove(@Param('id') id: string, @CurrentUser() user: IAuthUser) {
    await this.dataSourcesService.remove(id, user.tenantId);
    return { success: true };
  }
}
