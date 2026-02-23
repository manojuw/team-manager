import { Module } from '@nestjs/common';
import { DatabaseModule } from './modules/database/database.module';
import { AuthModule } from './modules/auth/auth.module';
import { ProjectsModule } from './modules/projects/projects.module';
import { DataSourcesModule } from './modules/datasources/datasources.module';
import { SyncModule } from './modules/sync/sync.module';
import { HealthModule } from './modules/health/health.module';

@Module({
  imports: [
    DatabaseModule,
    AuthModule,
    ProjectsModule,
    DataSourcesModule,
    SyncModule,
    HealthModule,
  ],
})
export class AppModule {}
