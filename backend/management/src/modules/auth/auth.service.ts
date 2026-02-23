import { Injectable, ConflictException, UnauthorizedException } from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import * as bcrypt from 'bcryptjs';
import { User } from '../database/entities/user.entity';
import { Tenant } from '../database/entities/tenant.entity';
import { SignupDto } from './dto/signup.dto';
import { LoginDto } from './dto/login.dto';
import { IAuthUser } from '@/common/interfaces/auth-user.interface';

@Injectable()
export class AuthService {
  constructor(
    @InjectRepository(User)
    private readonly userRepository: Repository<User>,
    @InjectRepository(Tenant)
    private readonly tenantRepository: Repository<Tenant>,
    private readonly jwtService: JwtService,
  ) {}

  async signup(dto: SignupDto) {
    const existing = await this.userRepository.findOne({ where: { email: dto.email } });
    if (existing) {
      throw new ConflictException('Email already registered');
    }

    const tenant = this.tenantRepository.create({ name: dto.tenantName });
    const savedTenant = await this.tenantRepository.save(tenant);

    const passwordHash = await bcrypt.hash(dto.password, 12);
    const user = this.userRepository.create({
      email: dto.email,
      password_hash: passwordHash,
      name: dto.name,
      tenant_id: savedTenant.id,
      role: 'admin',
    });
    const savedUser = await this.userRepository.save(user);

    const tokenPayload: IAuthUser = {
      userId: savedUser.id,
      tenantId: savedTenant.id,
      email: dto.email,
      name: dto.name,
      role: savedUser.role,
    };
    const token = this.jwtService.sign(tokenPayload);

    return {
      token,
      user: {
        id: savedUser.id,
        email: dto.email,
        name: dto.name,
        tenantId: savedTenant.id,
        role: savedUser.role,
      },
    };
  }

  async login(dto: LoginDto) {
    const user = await this.userRepository
      .createQueryBuilder('u')
      .innerJoinAndSelect('u.tenant', 't')
      .where('u.email = :email', { email: dto.email })
      .getOne();

    if (!user) {
      throw new UnauthorizedException('Invalid email or password');
    }

    const validPassword = await bcrypt.compare(dto.password, user.password_hash);
    if (!validPassword) {
      throw new UnauthorizedException('Invalid email or password');
    }

    const tokenPayload: IAuthUser = {
      userId: user.id,
      tenantId: user.tenant_id,
      email: user.email,
      name: user.name,
      role: user.role,
    };
    const token = this.jwtService.sign(tokenPayload);

    return {
      token,
      user: {
        id: user.id,
        email: user.email,
        name: user.name,
        tenantId: user.tenant_id,
        tenantName: user.tenant.name,
        role: user.role,
      },
    };
  }

  async getProfile(userId: string) {
    const user = await this.userRepository
      .createQueryBuilder('u')
      .innerJoinAndSelect('u.tenant', 't')
      .where('u.id = :id', { id: userId })
      .getOne();

    if (!user) {
      return null;
    }

    return {
      id: user.id,
      email: user.email,
      name: user.name,
      tenantId: user.tenant_id,
      tenantName: user.tenant.name,
      role: user.role,
    };
  }
}
