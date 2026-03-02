import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Tenant, User, Project, Connector, DataSource, SyncHistory, SemanticData } from './entities';

@Module({
  imports: [
    TypeOrmModule.forRoot({
      type: 'postgres',
      url: process.env.DATABASE_URL,
      entities: [Tenant, User, Project, Connector, DataSource, SyncHistory, SemanticData],
      synchronize: false,
      logging: false,
    }),
    TypeOrmModule.forFeature([Tenant, User, Project, Connector, DataSource, SyncHistory, SemanticData]),
  ],
  exports: [TypeOrmModule],
})
export class DatabaseModule {}
