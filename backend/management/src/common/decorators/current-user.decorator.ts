import { createParamDecorator, ExecutionContext } from '@nestjs/common';
import { IAuthUser } from '../interfaces/auth-user.interface';

export const CurrentUser = createParamDecorator(
  (data: keyof IAuthUser | undefined, ctx: ExecutionContext): IAuthUser | string => {
    const request = ctx.switchToHttp().getRequest();
    const user = request.user as IAuthUser;
    return data ? user[data] : user;
  },
);
